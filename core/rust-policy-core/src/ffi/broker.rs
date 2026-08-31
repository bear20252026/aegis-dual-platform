//! FfiBroker——UniFFI 有状态对象（H-4 拆分自 ffi.rs，行为不变）。

use super::*;

// ===== UniFFI Object（有状态对象——跨调用保持状态）=====

/// FFI 版 Broker——跨语言导航决策（委托 ContextBroker）。
///
/// 平台运行时接入须使用生成的绑定和受验证的原生制品；在此之前此类型仅定义共享边界。
/// 内部用 Mutex 提供可变性——UniFFI Object 方法只支持 &self（Arc 只读）。
#[derive(uniffi::Object)]
pub struct FfiBroker {
    inner: std::sync::Mutex<crate::broker::ContextBroker>,
    /// 仅允许消费本 Broker 签发且仍处于当前会话生命周期内的授权。
    /// 这阻止宿主伪造结构正确的 FFI 授权对象绕过策略评估。
    issued_actions: std::sync::Mutex<HashMap<String, IssuedAuthorization>>,
    /// 仅由策略核心登记的待审批动作；平台不能凭展示用请求重建授权。
    pending_navigation_approvals: std::sync::Mutex<HashMap<String, AuthorizedAction>>,
    policy_version: String,
}

/// 原生策略核心签发的授权状态。已消费记录保留到会话撤销，
/// 使精确重放仍可返回 `nonce_replay`，而不是退化为未签发。
#[derive(Debug, Clone)]
enum IssuedAuthorization {
    Pending(Box<AuthorizedAction>),
    Consumed { session_id: String },
}

impl IssuedAuthorization {
    fn session_id(&self) -> &str {
        match self {
            Self::Pending(action) => &action.session_id,
            Self::Consumed { session_id } => session_id,
        }
    }
}

#[uniffi::export]
impl FfiBroker {
    /// 创建 Broker（policy_version 锁定——INV-03 一致性）。
    #[uniffi::constructor]
    pub fn new(policy_version: String) -> Self {
        Self {
            inner: std::sync::Mutex::new(crate::broker::ContextBroker::new(
                policy_version.clone(),
                PolicyEngine::default(),
                CapabilityRegistry::new(),
            )),
            issued_actions: std::sync::Mutex::new(HashMap::new()),
            pending_navigation_approvals: std::sync::Mutex::new(HashMap::new()),
            policy_version,
        }
    }

    /// 评估导航意图（URL 解析 + 会话验证 → FfiDecision——fail-closed）。
    ///
    /// ⚠️ H-7 审计注记（2026-08-31）：本通路执行会话/代际/nonce 验证，
    /// 不含 policy.evaluate / capability.validate（后者默认 deny-all，
    /// 接线属产品级变更——见 broker.rs 模块文档 H-7 注记）。FFI 语义由
    /// 本文件 ffi_navigation_tests 回归测试锁定。
    pub fn evaluate_navigation(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        // URL 解析（fail-closed：解析失败 → Deny）
        let canonical_url = match crate::origin::canonicalize_external(&raw_url) {
            Some(p) => p,
            None => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "url_policy".into(),
                        detail: format!("拒绝 URL: {raw_url}"),
                        explanation: format!("denied origin — URL parsing failed: {raw_url}"),
                    },
                };
            }
        };
        let nonce = match generate_nonce() {
            Ok(value) => value,
            Err(reason) => return FfiDecision::Deny { reason },
        };
        let expires_at = match SystemTime::now().duration_since(UNIX_EPOCH) {
            Ok(duration) => duration.as_secs().saturating_add(120),
            Err(_) => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "system_clock".into(),
                        detail: "系统时间不可用".into(),
                        explanation: "denied — system clock is before UNIX epoch".into(),
                    },
                };
            }
        };
        let action = AuthorizedAction {
            session_id: session_id.clone(),
            tab_id: tab_id.clone(),
            document_generation: generation,
            origin: canonical_url.origin.clone(),
            method: "GET".into(),
            canonical_parameters: canonical_url.canonical_parameters,
            scope: scope.clone(),
            expires_at,
            nonce,
            policy_version: self.policy_version.clone(),
            explanation: format!(
                "allowed origin {} — scheme {}, host {}",
                canonical_url.origin, canonical_url.scheme, canonical_url.host
            ),
        };
        // 会话验证（fail-closed）
        let guard = self.inner.lock().map_err(|_| ()).ok();
        let decision = match guard {
            Some(g) => g.validate_action(&action),
            None => Decision::Deny(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        match decision {
            Decision::Allow(authorized) => match self.issued_actions.lock() {
                Ok(mut issued_actions) => {
                    issued_actions.insert(
                        authorized.nonce.clone(),
                        IssuedAuthorization::Pending(Box::new(authorized.clone())),
                    );
                    FfiDecision::Allow {
                        action: FfiAuthorizedAction::from(authorized),
                    }
                }
                Err(_) => FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "authorization_ledger".into(),
                        detail: "授权账本锁获取失败".into(),
                        explanation: "denied — issued authorization ledger lock poisoned".into(),
                    },
                },
            },
            other => FfiDecision::from(other),
        }
    }

    /// 将当前导航登记为待审批请求。它复用完整的策略评估和会话验证，
    /// 但不会向宿主发放可消费授权；只有同一 Broker 的显式批准才能兑换原始动作。
    pub fn request_navigation_confirmation(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        let authorized =
            match self.evaluate_navigation(session_id, tab_id, generation, raw_url, scope) {
                FfiDecision::Allow { action } => AuthorizedAction {
                    session_id: action.session_id,
                    tab_id: action.tab_id,
                    document_generation: action.document_generation,
                    origin: action.origin,
                    method: action.method,
                    canonical_parameters: action.canonical_parameters,
                    scope: action.scope,
                    expires_at: action.expires_at,
                    nonce: action.nonce,
                    policy_version: action.policy_version,
                    explanation: action.explanation,
                },
                other => return other,
            };
        let removed_from_issued = match self.issued_actions.lock() {
            Ok(mut issued_actions) => matches!(
                issued_actions.remove(&authorized.nonce),
                Some(IssuedAuthorization::Pending(issued)) if *issued == authorized
            ),
            Err(_) => {
                return ffi_deny(
                    "authorization_ledger",
                    "授权账本锁获取失败",
                    "denied — issued authorization ledger lock poisoned",
                );
            }
        };
        if !removed_from_issued {
            return ffi_deny(
                "authorization_ledger",
                "策略核心未能登记待审批授权",
                "denied — evaluated authorization was missing from the issued ledger",
            );
        }
        let request = FfiApprovalRequest {
            origin: authorized.origin.clone(),
            method: authorized.method.clone(),
            path: authorized.canonical_parameters.clone(),
            scope: authorized.scope.clone(),
            expires_at: authorized.expires_at,
            nonce: authorized.nonce.clone(),
        };
        match self.pending_navigation_approvals.lock() {
            Ok(mut pending_approvals) => {
                pending_approvals.insert(authorized.nonce.clone(), authorized);
                FfiDecision::RequireConfirmation { request }
            }
            Err(_) => ffi_deny(
                "approval_ledger",
                "待审批账本锁获取失败",
                "denied — pending approval ledger lock poisoned",
            ),
        }
    }

    /// 显式批准当前待审批导航。该入口仅兑换策略核心保留的精确授权，
    /// 并再次绑定当前 URL/scope、会话、代际、策略版本与过期时间。
    pub fn approve_navigation_confirmation(
        &self,
        nonce: String,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        if nonce.is_empty() {
            return ffi_deny(
                "approval_not_pending",
                "审批 nonce 为空",
                "denied — approval nonce was empty",
            );
        }
        let authorized = match self.pending_navigation_approvals.lock() {
            Ok(mut pending_approvals) => pending_approvals.remove(&nonce),
            Err(_) => {
                return ffi_deny(
                    "approval_ledger",
                    "待审批账本锁获取失败",
                    "denied — pending approval ledger lock poisoned",
                );
            }
        };
        let Some(authorized) = authorized else {
            return ffi_deny(
                "approval_not_pending",
                "审批请求不存在、已拒绝或已兑换",
                "denied — approval request was not pending",
            );
        };
        let Some(canonical_url) = crate::origin::canonicalize_external(&raw_url) else {
            return deny_url(raw_url);
        };
        if authorized.method != "GET"
            || authorized.scope != scope
            || authorized.origin != canonical_url.origin
            || authorized.canonical_parameters != canonical_url.canonical_parameters
        {
            return ffi_deny(
                "approval_binding_mismatch",
                "审批请求与当前导航参数不匹配",
                "denied — approval URL or scope no longer matches the pending request",
            );
        }
        let decision = match self.inner.lock() {
            Ok(broker) => broker.validate_action(&authorized),
            Err(_) => Decision::Deny(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        let Decision::Allow(authorized) = decision else {
            return FfiDecision::from(decision);
        };
        match self.issued_actions.lock() {
            Ok(mut issued_actions) => {
                issued_actions.insert(
                    authorized.nonce.clone(),
                    IssuedAuthorization::Pending(Box::new(authorized.clone())),
                );
                FfiDecision::Allow {
                    action: FfiAuthorizedAction::from(authorized),
                }
            }
            Err(_) => ffi_deny(
                "authorization_ledger",
                "授权账本锁获取失败",
                "denied — issued authorization ledger lock poisoned",
            ),
        }
    }

    /// 显式拒绝待审批导航。未知、已过期、已兑换或已拒绝的 nonce 一律返回 false。
    pub fn reject_navigation_confirmation(&self, nonce: String) -> bool {
        if nonce.is_empty() {
            return false;
        }
        match self.pending_navigation_approvals.lock() {
            Ok(mut pending_approvals) => pending_approvals.remove(&nonce).is_some(),
            Err(_) => false,
        }
    }

    /// 创建新会话（ttl 秒）。
    pub fn create_session(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        ttl_seconds: u64,
    ) -> bool {
        match self.inner.lock() {
            Ok(mut g) => {
                g.create_session(
                    session_id,
                    tab_id,
                    generation,
                    std::time::Duration::from_secs(ttl_seconds),
                );
                true
            }
            Err(_) => false,
        }
    }

    /// 销毁会话。
    pub fn destroy_session(&self, session_id: String) -> bool {
        let destroyed = match self.inner.lock() {
            Ok(mut g) => {
                g.destroy_session(&session_id);
                true
            }
            Err(_) => false,
        };
        if let Ok(mut issued_actions) = self.issued_actions.lock() {
            issued_actions.retain(|_, authorization| authorization.session_id() != session_id);
        }
        if let Ok(mut pending_approvals) = self.pending_navigation_approvals.lock() {
            pending_approvals.retain(|_, action| action.session_id != session_id);
        }
        destroyed
    }

    /// 顶层文档切换后推进会话代际；错标签、跳跃与回退均拒绝。
    pub fn advance_document_generation(
        &self,
        session_id: String,
        tab_id: String,
        next_generation: u64,
    ) -> bool {
        let advanced = match self.inner.lock() {
            Ok(mut broker) => {
                broker.advance_document_generation(&session_id, &tab_id, next_generation)
            }
            Err(_) => false,
        };
        if advanced {
            if let Ok(mut issued_actions) = self.issued_actions.lock() {
                issued_actions.retain(|_, authorization| authorization.session_id() != session_id);
            }
            if let Ok(mut pending_approvals) = self.pending_navigation_approvals.lock() {
                pending_approvals.retain(|_, action| action.session_id != session_id);
            }
        }
        advanced
    }

    /// 在导航副作用执行点校验当前 URL/scope 并消费授权，拒绝参数替换或 nonce 重放。
    pub fn consume_navigation(
        &self,
        action: FfiAuthorizedAction,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        let Some(canonical_url) = crate::origin::canonicalize_external(&raw_url) else {
            return deny_url(raw_url);
        };
        let action = AuthorizedAction {
            session_id: action.session_id,
            tab_id: action.tab_id,
            document_generation: action.document_generation,
            origin: action.origin,
            method: action.method,
            canonical_parameters: action.canonical_parameters,
            scope: action.scope,
            expires_at: action.expires_at,
            nonce: action.nonce,
            policy_version: action.policy_version,
            explanation: action.explanation,
        };
        if action.method != "GET"
            || action.scope != scope
            || action.origin != canonical_url.origin
            || action.canonical_parameters != canonical_url.canonical_parameters
        {
            return FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: "action_binding_mismatch".into(),
                    detail: "授权动作与当前导航参数不匹配".into(),
                    explanation: "denied — action origin, path/query, method, or scope changed"
                        .into(),
                },
            };
        }
        let issued_action = match self.issued_actions.lock() {
            Ok(issued_actions) => issued_actions.get(&action.nonce).cloned(),
            Err(_) => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "authorization_ledger".into(),
                        detail: "授权账本锁获取失败".into(),
                        explanation: "denied — issued authorization ledger lock poisoned".into(),
                    },
                };
            }
        };
        match issued_action {
            Some(IssuedAuthorization::Pending(issued)) if *issued == action => {}
            Some(IssuedAuthorization::Consumed { .. }) => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "nonce_replay".into(),
                        detail: "授权动作已被消费".into(),
                        explanation: "denied — issued authorization nonce already consumed".into(),
                    },
                };
            }
            _ => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "action_not_issued".into(),
                        detail: "授权动作不是当前策略核心签发或已被撤销".into(),
                        explanation: "denied — action was not issued by this broker or was revoked"
                            .into(),
                    },
                };
            }
        }
        let decision = match self.inner.lock() {
            Ok(mut broker) => broker.validate_and_consume(&action),
            Err(_) => Decision::Deny(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        if matches!(decision, Decision::Allow(_)) {
            if let Ok(mut issued_actions) = self.issued_actions.lock() {
                issued_actions.insert(
                    action.nonce.clone(),
                    IssuedAuthorization::Consumed {
                        session_id: action.session_id.clone(),
                    },
                );
            }
        }
        FfiDecision::from(decision)
    }
}

fn deny_url(raw_url: String) -> FfiDecision {
    FfiDecision::Deny {
        reason: FfiDenyReason {
            code: "url_policy".into(),
            detail: format!("拒绝 URL: {raw_url}"),
            explanation: format!("denied origin — URL parsing failed: {raw_url}"),
        },
    }
}

fn ffi_deny(code: &str, detail: &str, explanation: &str) -> FfiDecision {
    FfiDecision::Deny {
        reason: FfiDenyReason {
            code: code.into(),
            detail: detail.into(),
            explanation: explanation.into(),
        },
    }
}

fn generate_nonce() -> Result<String, FfiDenyReason> {
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).map_err(|error| FfiDenyReason {
        code: "entropy_unavailable".into(),
        detail: "无法生成安全随机 nonce".into(),
        explanation: format!("denied — operating-system entropy unavailable: {error}"),
    })?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

// ============================ H-7 审计回归测试 ============================ //
// 审计 2026-08-31：FfiBroker 导航通路执行的是「会话/代际/nonce」验证，
// 策略层（PolicyEngine）与能力层（CapabilityRegistry）仅在嵌入式宿主直接
// 使用 ContextBroker::evaluate 时生效（见 broker.rs 模块文档）。以下测试
// 锁定 FFI 通路的 fail-closed 语义，防止该口径被无声变更。

#[cfg(test)]
mod ffi_navigation_tests {
    use super::*;

    const POLICY_VERSION: &str = "test-policy-1";

    #[test]
    fn evaluate_navigation_denies_unknown_session() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        let decision = broker.evaluate_navigation(
            "no-such-session".into(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::Deny { .. }),
            "未知会话必须拒绝（fail-closed）"
        );
    }

    #[test]
    fn evaluate_navigation_allows_valid_session() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "tab-1".into(), 1, 60));
        let decision = broker.evaluate_navigation(
            "s1".into(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(
                decision,
                FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
            ),
            "有效会话 + 可解析 https URL 应放行或要求确认"
        );
    }

    #[test]
    fn evaluate_navigation_denies_unparseable_url() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s2".into(), "tab-1".into(), 1, 60));
        let decision = broker.evaluate_navigation(
            "s2".into(),
            "tab-1".into(),
            1,
            "file:///etc/passwd".into(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::Deny { .. }),
            "file:// 非 http(s) scheme 必须在 URL 解析层拒绝"
        );
    }
}

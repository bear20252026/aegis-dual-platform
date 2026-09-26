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

/// M-15 修复（审计 2026-08-31）：授权账本上限——镜像 consumed_nonces 的
/// fail-closed 模式（满时先惰性清理，仍满即拒绝，绝不无界增长）。
const MAX_ISSUED_ACTIONS: usize = 50_000;

/// P1-10 修复（全量复审 2026-09-01）：导航授权动作有效期（秒）——
/// 原 120 为硬编码字面量（无语义名、多处漂移风险）。注意与「会话 TTL」
/// 是两个概念：这是签发授权的可消费窗口，超期后 consume 过期拒绝。
const ACTION_EXPIRY_SECONDS: u64 = 120;
/// 审计整改（2026-09-07）：待审批导航账本上限。此前无容量/清理——可被
/// 待审批请求堆叠造成内存 DoS；满则 fail-closed 拒绝（镜像 MAX_ISSUED_ACTIONS）。
const MAX_PENDING_APPROVALS: usize = 1024;
/// P1-11 修复（全量复审 2026-09-01）：FFI create_session 的 TTL 下限（秒）。
/// 宿主传 0 会得到"返回成功、即刻过期"的静默失效会话——钳到下限保底。
const MIN_SESSION_TTL_SECONDS: u64 = 30;
/// RS-158（审计 2026-09-25）：FFI create_session 的 TTL 上限（秒，24h）——
/// 与下限对称的钳制口径。此前上限自由：宿主可传 u64::MAX 使会话近乎永生，
/// 会话与 nonce/授权账本的驻留暴露面随之无界。超过钳到上限；常驻 persona
/// 会话按宿主约定应显式续期（RS-033 replace 语义）而非一次签发永生会话。
/// 会话总量的内存上限另由 M-16 会话池 fail-closed 容量约束（两个正交维度）。
const MAX_SESSION_TTL_SECONDS: u64 = 86_400;

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
    /// 职责边界（H-7）：本通路仅执行会话/代际/nonce 验证，policy.evaluate /
    /// capability.validate 未接入 FFI 通路——单一事实源见 broker.rs 模块文档
    /// H-7 审计注记，FFI 语义由本文件 ffi_navigation_tests 回归测试锁定。
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
            Ok(duration) => duration.as_secs().saturating_add(ACTION_EXPIRY_SECONDS),
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
        // RS-160（审计 2026-09-25）：参数在此处 move 进 action——三者在
        // 本函数后续不再使用，此前多余的 .clone() 每导航三次堆分配
        let action = AuthorizedAction {
            session_id,
            tab_id,
            document_generation: generation,
            origin: canonical_url.origin.clone(),
            method: "GET".into(),
            canonical_parameters: canonical_url.canonical_parameters,
            scope,
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
                    // M-15 修复（审计 2026-08-31）：账本容量 fail-closed
                    if !ledger_can_admit(&mut issued_actions) {
                        return ffi_deny(
                            "authorization_ledger_full",
                            "授权账本已达上限（惰性清理后仍满）",
                            "denied — authorization ledger exhausted its fail-closed capacity",
                        );
                    }
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
                FfiDecision::Allow { action } => AuthorizedAction::from(action),
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
                // 审计整改：有界账本——满则 fail-closed 拒绝（此前无上限，
                // 可被待审批请求堆叠造成内存 DoS）
                if pending_approvals.len() >= MAX_PENDING_APPROVALS {
                    // RS-035（审计 2026-09-24）：满时先清理已过期待审批——
                    // 此前过期请求永久驻留，1024 满后新请求被自拒绝服务
                    let now = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map(|duration| duration.as_secs())
                        .unwrap_or(u64::MAX);
                    pending_approvals.retain(|_, action| action.expires_at >= now);
                    if pending_approvals.len() >= MAX_PENDING_APPROVALS {
                        return ffi_deny(
                            "approval_ledger",
                            "待审批账本已达上限（1024）",
                            "denied — pending approval ledger at capacity",
                        );
                    }
                }
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
                // M-15 修复（审计 2026-08-31）：账本容量 fail-closed——
                // 满时先惰性清理过期 Pending，仍满则拒绝签发（绝不无界增长）
                if !ledger_can_admit(&mut issued_actions) {
                    return ffi_deny(
                        "authorization_ledger_full",
                        "授权账本已达上限（惰性清理后仍满）",
                        "denied — authorization ledger exhausted its fail-closed capacity",
                    );
                }
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
    ///
    /// P1-11 修复（全量复审 2026-09-01）：TTL 下限钳制——宿主传 0 会
    /// 得到"签发成功、即刻过期"的静默失效会话（fail-open 陷阱面）。
    /// 钳到 MIN_SESSION_TTL_SECONDS 保底；RS-158：上限同样钳制到
    /// MAX_SESSION_TTL_SECONDS（24h）——超长 TTL 会话近乎永生，扩大
    /// 授权/nonce 账本驻留暴露面。
    ///
    /// RS-159：空 session_id 拒绝（fail-closed，与 contracts Action schema
    /// 的 minLength 1 对齐）——空 id 会话即匿名共享会话，任何传空 id 的
    /// 调用方都会落到同一会话，破坏 persona 隔离语义。
    pub fn create_session(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        ttl_seconds: u64,
    ) -> bool {
        if session_id.is_empty() {
            return false;
        }
        let effective_ttl = ttl_seconds.clamp(MIN_SESSION_TTL_SECONDS, MAX_SESSION_TTL_SECONDS);
        match self.inner.lock() {
            // M-16 修复（审计 2026-08-31）：会话池满（fail-closed）时
            // 返回 false——原实现无条件 true，掩盖了容量拒绝
            Ok(mut g) => g
                .create_session(
                    session_id,
                    tab_id,
                    generation,
                    std::time::Duration::from_secs(effective_ttl),
                )
                .is_some(),
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
    /// 绑定性比较：仅比较安全绑定属性，**不含 explanation**（人类可读审计
    /// 文本，不参与权限判定）。此前用 `*issued == action`（含 explanation），
    /// 而托管端序列化 NativeAction 不携带 explanation，导致合法一次消费被
    /// 误判 action_not_issued（"安装版崩溃"排查中暴露的确定性缺陷）。
    pub fn consume_navigation(
        &self,
        action: FfiAuthorizedAction,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        let Some(canonical_url) = crate::origin::canonicalize_external(&raw_url) else {
            return deny_url(raw_url);
        };
        let action = AuthorizedAction::from(action);
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
            Some(IssuedAuthorization::Pending(issued)) if same_binding(&issued, &action) => {}
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
                // M-15 修复（审计 2026-08-31）：Consumed 记录同样受账本
                // 上限约束（惰性清理过期 Pending 后仍满 → 本次导航转为
                // Deny——nonce 已被 validate_and_consume 消费，重放天然
                // 失败，fail-closed 语义保持闭合）
                if !ledger_can_admit(&mut issued_actions) {
                    return ffi_deny(
                        "authorization_ledger_full",
                        "授权账本已达上限（惰性清理后仍满）",
                        "denied — authorization ledger exhausted its fail-closed capacity",
                    );
                }
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

/// 绑定性比较：仅比较安全绑定属性，**不含 explanation**（人类可读审计
/// 文本，不参与权限判定）。此前 consume 用 `*issued == action`（含
/// explanation），而托管端序列化 NativeAction 不携带 explanation，
/// 导致合法一次消费被误判 action_not_issued（确定性缺陷）。
fn same_binding(a: &AuthorizedAction, b: &AuthorizedAction) -> bool {
    a.session_id == b.session_id
        && a.tab_id == b.tab_id
        && a.document_generation == b.document_generation
        && a.origin == b.origin
        && a.method == b.method
        && a.canonical_parameters == b.canonical_parameters
        && a.scope == b.scope
        && a.expires_at == b.expires_at
        && a.nonce == b.nonce
        && a.policy_version == b.policy_version
}

/// M-15 修复（审计 2026-08-31）：授权账本容量门（fail-closed）。
/// 未达上限直接放行；达上限先惰性清理已过期的 Pending 记录
/// （Consumed 记录保留到会话撤销，不参与清理），仍满则拒绝登记。
///
/// RS-136（审计 2026-09-25）：原子性契约——本函数与随后的
/// `issued_actions.insert(...)` **必须处在同一次
/// `issued_actions.lock()` 持有窗口内**（检查-插入不可跨锁拆分）。
/// 拆分即 TOCTOU：两个并发 evaluate 在各自持锁窗口内检查通过、
/// 交错插入，账本容量被突破（M-15 fail-closed 语义失效）。现有
/// 三处调用点（evaluate / approve / consume）均满足单锁窗口。
fn ledger_can_admit(issued: &mut HashMap<String, IssuedAuthorization>) -> bool {
    if issued.len() < MAX_ISSUED_ACTIONS {
        return true;
    }
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(u64::MAX);
    issued.retain(|_, authorization| match authorization {
        IssuedAuthorization::Pending(action) => action.expires_at >= now,
        IssuedAuthorization::Consumed { .. } => true,
    });
    issued.len() < MAX_ISSUED_ACTIONS
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
    const HEX_TABLE: &[u8; 16] = b"0123456789abcdef";
    let mut bytes = [0u8; 32];
    // RS-153：getrandom 0.3 API——getrandom() 更名 fill()
    getrandom::fill(&mut bytes).map_err(|error| FfiDenyReason {
        code: "entropy_unavailable".into(),
        detail: "无法生成安全随机 nonce".into(),
        explanation: format!("denied — operating-system entropy unavailable: {error}"),
    })?;
    // RS-137（审计 2026-09-25）：查表拼接替代 32 次 format! 堆分配
    // （每次导航 32 个临时 String → 预分配单缓冲零临时分配）
    let mut out = String::with_capacity(64);
    for byte in bytes {
        out.push(HEX_TABLE[(byte >> 4) as usize] as char);
        out.push(HEX_TABLE[(byte & 0x0f) as usize] as char);
    }
    Ok(out)
}

// ============================ H-7 审计回归测试 ============================ //
// 锁定 FFI 导航通路的 fail-closed 语义（仅会话/代际/nonce 验证，policy/
// capability 层未接线）——职责边界的完整背景与决策记录以 broker.rs 模块文档
// H-7 注记为单一事实源，此处不再重复展开。

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

    /// P1-11 回归（全量复审 2026-09-01）：ttl=0 必须钳到下限——
    /// 原实现会签发"成功、即刻过期"的静默失效会话。
    #[test]
    fn create_session_clamps_zero_ttl_to_minimum() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s-min".into(), "tab-1".into(), 1, 0));
        let decision = broker.evaluate_navigation(
            "s-min".into(),
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
            "ttl=0 钳到 MIN_SESSION_TTL_SECONDS 后会话应在窗口内有效"
        );
    }

    // —— RS-158（审计 2026-09-25）：TTL 上限钳制 ——

    #[test]
    fn create_session_clamps_huge_ttl_to_maximum() {
        // u64::MAX 会话近乎永生——必须钳到 MAX_SESSION_TTL_SECONDS（24h）。
        // 实际生效 TTL 经 core session_ttl 可观测性 API 读取（测试不可
        // 反射宿主传参，只认签发结果）。
        // 注意：锁作用域最小化——持有 inner 锁期间不得再调
        // broker.create_session（内部二次 lock 同一 Mutex = 自死锁）
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s-max".into(), "tab-1".into(), 1, u64::MAX));
        {
            let inner = broker.inner.lock().expect("broker 锁必须可用");
            assert_eq!(
                inner.session_ttl("s-max"),
                Some(std::time::Duration::from_secs(MAX_SESSION_TTL_SECONDS)),
                "超长 TTL 必须钳到 24h 上限"
            );
        }
        // 边界内侧：86400 恰好等于上限——原样接受（锁已释放，安全再入）
        assert!(broker.create_session("s-cap".into(), "tab-1".into(), 1, 86_400));
        let inner = broker.inner.lock().expect("broker 锁必须可用");
        assert_eq!(
            inner.session_ttl("s-cap"),
            Some(std::time::Duration::from_secs(86_400)),
            "恰等于上限的 TTL 原样生效"
        );
    }

    // —— RS-159（审计 2026-09-25）：session_id 直测 ——

    #[test]
    fn create_session_rejects_empty_session_id() {
        // 空 session_id 拒绝（fail-closed，对齐 Action schema minLength 1）——
        // 空 id 会话即匿名共享会话，破坏 persona 隔离语义
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(!broker.create_session(String::new(), "tab-1".into(), 1, 60));
        // 创建失败即无会话——后续导航必须拒绝（fail-closed 闭环）
        let decision = broker.evaluate_navigation(
            String::new(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::Deny { .. }),
            "空 id 会话不存在——导航必须拒绝"
        );
    }

    #[test]
    fn create_session_session_id_uniqueness_and_isolation() {
        // session_id 隔离语义直测：同 id replace（RS-033 续期契约）+
        // 异 id 各自独立（不同 id 不串会话）
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("sa".into(), "tab-a".into(), 1, 60));
        assert!(broker.create_session("sb".into(), "tab-b".into(), 1, 60));
        // sa 的会话不能在 tab-b 上用（会话 ↔ 标签绑定）
        let cross = broker.evaluate_navigation(
            "sa".into(),
            "tab-b".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(cross, FfiDecision::Deny { .. }),
            "跨标签复用会话必须拒绝"
        );
        // 同 id replace 语义（续期）——与 RS-033 契约一致
        assert!(broker.create_session("sa".into(), "tab-a".into(), 1, 120));
    }

    // —— RS-135（审计 2026-09-25）：容量/清理/覆盖语义 ——

    #[test]
    fn destroy_session_clears_issued_and_pending_ledgers() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
        let FfiDecision::Allow { action } = broker.evaluate_navigation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/a".into(),
            "navigation".into(),
        ) else {
            panic!("expected allow");
        };
        let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/b".into(),
            "navigation".into(),
        ) else {
            panic!("expected pending");
        };
        assert!(broker.destroy_session("s1".into()));
        // 已签发授权随销毁清理（不退化为 nonce_replay——是撤销）
        match broker.consume_navigation(action, "https://example.com/a".into(), "navigation".into())
        {
            FfiDecision::Deny { reason } => {
                assert_ne!(reason.code, "nonce_replay", "销毁清理 ≠ 已消费重放");
            }
            _ => panic!("destroyed session must not consume"),
        }
        // 待审批请求随销毁清理
        match broker.approve_navigation_confirmation(
            request.nonce,
            "https://example.com/b".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_not_pending"),
            _ => panic!("pending approval must be revoked on session destroy"),
        }
    }

    #[test]
    fn reject_and_empty_nonce_are_fail_closed() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
        // 未知 nonce / 空 nonce / 已拒绝后的二次拒绝——一律 false
        assert!(!broker.reject_navigation_confirmation("no-such".into()));
        assert!(!broker.reject_navigation_confirmation(String::new()));
        let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/c".into(),
            "navigation".into(),
        ) else {
            panic!("expected pending");
        };
        assert!(broker.reject_navigation_confirmation(request.nonce.clone()));
        assert!(
            !broker.reject_navigation_confirmation(request.nonce),
            "二次拒绝 false"
        );
        // 空 nonce 的审批入口同样 fail-closed
        match broker.approve_navigation_confirmation(
            String::new(),
            "https://example.com/c".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_not_pending"),
            _ => panic!("empty nonce must not approve"),
        }
    }

    #[test]
    fn pending_approval_capacity_is_fail_closed() {
        // MAX_PENDING_APPROVALS=1024：填满后第 1025 个请求 fail-closed
        // 拒绝（此前无上限可堆叠内存 DoS）；全部未过期，惰性清理不腾位
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
        for i in 0..MAX_PENDING_APPROVALS {
            let url = format!("https://example.com/pending/{i}");
            let decision = broker.request_navigation_confirmation(
                "s1".into(),
                "t1".into(),
                0,
                url.clone(),
                "navigation".into(),
            );
            assert!(
                matches!(decision, FfiDecision::RequireConfirmation { .. }),
                "第 {i} 个待审批请求必须登记成功"
            );
        }
        let overflow = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/overflow".into(),
            "navigation".into(),
        );
        match overflow {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_ledger"),
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. } => {
                panic!("capacity overflow must deny")
            }
        }
    }

    #[test]
    fn create_session_same_id_replaces_prior_generation() {
        // RS-033 契约在 FFI 层的镜像：同 id create_session = 显式 replace——
        // 旧代际授权/验证立即失效，新代际生效
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 1, 60));
        assert!(broker.create_session("s1".into(), "t1".into(), 2, 60));
        assert!(
            matches!(
                broker.evaluate_navigation(
                    "s1".into(),
                    "t1".into(),
                    1,
                    "https://example.com/".into(),
                    "navigation".into(),
                ),
                FfiDecision::Deny { .. }
            ),
            "replace 后旧代际必须失效"
        );
        assert!(matches!(
            broker.evaluate_navigation(
                "s1".into(),
                "t1".into(),
                2,
                "https://example.com/".into(),
                "navigation".into(),
            ),
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
        ));
    }

    // —— RS-136（审计 2026-09-25）：ledger_can_admit 白盒直测 ——

    fn craft_action(expires_in: i64) -> AuthorizedAction {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        AuthorizedAction {
            session_id: "s".into(),
            tab_id: "t".into(),
            document_generation: 0,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/".into(),
            scope: "navigation".into(),
            expires_at: (now as i64 + expires_in) as u64,
            nonce: format!("nonce-{expires_in}-{}", std::process::id()),
            policy_version: "test".into(),
            explanation: String::new(),
        }
    }

    #[test]
    fn ledger_can_admit_direct_capacity_semantics() {
        let mut ledger: HashMap<String, IssuedAuthorization> = HashMap::new();
        // 未满：直接放行
        ledger.insert(
            "n1".into(),
            IssuedAuthorization::Pending(Box::new(craft_action(3600))),
        );
        assert!(ledger_can_admit(&mut ledger));
        // 满 + 全部未过期 Pending：拒绝（fail-closed，不淘汰）
        let mut full: HashMap<String, IssuedAuthorization> = HashMap::new();
        for i in 0..MAX_ISSUED_ACTIONS {
            full.insert(
                format!("k{i}"),
                IssuedAuthorization::Pending(Box::new(craft_action(3600))),
            );
        }
        assert!(!ledger_can_admit(&mut full));
        // 满 + 存在过期 Pending：惰性清理后放行（清理不触及 Consumed）
        let key0 = "k0".to_string();
        full.insert(
            key0.clone(),
            IssuedAuthorization::Pending(Box::new(craft_action(-1))),
        );
        assert!(ledger_can_admit(&mut full));
        assert!(!full.contains_key(&key0), "过期 Pending 被清理");
        assert_eq!(
            full.len(),
            MAX_ISSUED_ACTIONS - 1,
            "清理仅腾位不扩容（insert 由调用方随后完成）"
        );
        // 拒绝路径：已满且全部为 Consumed（清理不触及）→ 拒绝
        let mut consumed_full: HashMap<String, IssuedAuthorization> = HashMap::new();
        for i in 0..MAX_ISSUED_ACTIONS {
            consumed_full.insert(
                format!("c{i}"),
                IssuedAuthorization::Consumed {
                    session_id: "s".into(),
                },
            );
        }
        assert!(!ledger_can_admit(&mut consumed_full));
    }
}

// —— RS-137（审计 2026-09-25）：nonce 查表实现回归 ——

#[cfg(test)]
mod nonce_tests {
    use super::*;

    #[test]
    fn generate_nonce_is_64_lowercase_hex_chars() {
        for _ in 0..8 {
            let nonce = generate_nonce().expect("OS entropy available in tests");
            assert_eq!(nonce.len(), 64, "32 字节 hex 编码必须 64 字符");
            assert!(
                nonce
                    .bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
                "nonce 必须全小写 hex（与 MAX_NONCE_LENGTH 校验、账本键序一致）"
            );
        }
        // 两次生成不重复（随机性抽查）
        let a = generate_nonce().unwrap();
        let b = generate_nonce().unwrap();
        assert_ne!(a, b);
    }
}

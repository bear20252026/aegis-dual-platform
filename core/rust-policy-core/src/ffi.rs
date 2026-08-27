// 由账号2生成
//! UniFFI 跨语言 FFI 导出层（官方规范 0.32——proc-macro 模式）。
//!
//! 包装 Rust policy-core 的 Broker/Decision/Origin 类型，
//! 供 C#/Kotlin/Python 通过 FFI 调用——消除跨平台三语言重复。
//!
//! 设计原则：
//! - 不修改内部类型（decision.rs/broker.rs 保持纯 Rust），仅包装
//! - 所有 FFI 类型使用 UniFFI derive（Record/Enum/Object）
//! - setup_scaffolding!() 在 crate 根调用（官方要求）
//! - library mode 绑定生成（官方推荐——proc-macro 必须用 library mode）

use crate::decision::{AuthorizedAction, Decision, DenyReason};
use std::time::{SystemTime, UNIX_EPOCH};

// ===== UniFFI 类型包装（Record/Enum）=====

/// FFI 版授权行动（与 decision::AuthorizedAction 字段一致）。
#[derive(uniffi::Record)]
pub struct FfiAuthorizedAction {
    pub session_id: String,
    pub tab_id: String,
    pub document_generation: u64,
    pub origin: String,
    pub method: String,
    pub canonical_parameters: String,
    pub scope: String,
    pub expires_at: u64,
    pub nonce: String,
    pub policy_version: String,
    pub explanation: String,
}

impl From<AuthorizedAction> for FfiAuthorizedAction {
    fn from(a: AuthorizedAction) -> Self {
        Self {
            session_id: a.session_id,
            tab_id: a.tab_id,
            document_generation: a.document_generation,
            origin: a.origin,
            method: a.method,
            canonical_parameters: a.canonical_parameters,
            scope: a.scope,
            expires_at: a.expires_at,
            nonce: a.nonce,
            policy_version: a.policy_version,
            explanation: a.explanation,
        }
    }
}

/// FFI 版拒绝原因。
#[derive(uniffi::Record)]
pub struct FfiDenyReason {
    pub code: String,
    pub detail: String,
    pub explanation: String,
}

/// FFI 版安全决策（枚举——Allow/Deny/RequireConfirmation）。
#[derive(uniffi::Enum)]
pub enum FfiDecision {
    Allow { action: FfiAuthorizedAction },
    RequireConfirmation { origin: String, method: String },
    Deny { reason: FfiDenyReason },
}

impl From<Decision> for FfiDecision {
    fn from(d: Decision) -> Self {
        match d {
            Decision::Allow(a) => FfiDecision::Allow {
                action: FfiAuthorizedAction::from(a),
            },
            Decision::RequireConfirmation(request) => FfiDecision::RequireConfirmation {
                origin: request.origin,
                method: request.method,
            },
            Decision::Deny(r) => FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: r.code,
                    detail: r.detail,
                    explanation: r.explanation,
                },
            },
        }
    }
}

// ===== FFI 导出函数（#[uniffi::export]）=====

/// FFI 版 URL 解析结果（UniFFI 不支持元组返回——用 Record）。
#[derive(uniffi::Record)]
pub struct FfiOrigin {
    pub scheme: String,
    pub host: String,
}

/// URL 校验（委托 origin 模块——消除 C#/Kotlin/Python 重复实现）。
///
/// 返回 `FfiOrigin { scheme, host }` 或 None（URL 非法）。
#[uniffi::export]
pub fn try_parse_external(raw_url: String) -> Option<FfiOrigin> {
    crate::origin::try_parse_external(&raw_url).map(|(scheme, host)| FfiOrigin { scheme, host })
}

/// URL 主机名提取（委托 util 模块）。
#[uniffi::export]
pub fn extract_host(url: String) -> Option<String> {
    crate::util::extract_host(&url)
}

/// 生成指纹防护管道 JS（委托 fingerprint_pipeline 逻辑——跨端统一）。
#[uniffi::export]
pub fn build_fingerprint_pipeline(session_seed: String) -> String {
    // 注：fingerprint_pipeline 的 JS 生成在 Python 侧（legacy），
    // Rust 侧提供 seed 派生；此处导出便于后续迁移。
    crate::shield::FingerprintShield::from_seed(hex_seed_to_bytes(&session_seed)).inject_script()
}

/// 十六进制种子转字节数组（内部辅助）。
fn hex_seed_to_bytes(hex: &str) -> [u8; 32] {
    let mut out = [0u8; 32];
    let bytes = hex.as_bytes();
    for i in 0..32 {
        if i * 2 + 1 < bytes.len() {
            let hi = crate::util::hex_digit(bytes[i * 2]).unwrap_or(0);
            let lo = crate::util::hex_digit(bytes[i * 2 + 1]).unwrap_or(0);
            out[i] = (hi << 4) | lo;
        }
    }
    out
}

// ===== UniFFI Object（有状态对象——跨调用保持状态）=====

/// FFI 版 Broker——跨语言导航决策（委托 ContextBroker）。
///
/// C#/Kotlin/Python 各自实例化，替代三语言重复的 Broker 实现。
/// 内部用 Mutex 提供可变性——UniFFI Object 方法只支持 &self（Arc 只读）。
#[derive(uniffi::Object)]
pub struct FfiBroker {
    inner: std::sync::Mutex<crate::broker::ContextBroker>,
    policy_version: String,
}

#[uniffi::export]
impl FfiBroker {
    /// 创建 Broker（policy_version 锁定——INV-03 一致性）。
    #[uniffi::constructor]
    pub fn new(policy_version: String) -> Self {
        Self {
            inner: std::sync::Mutex::new(crate::broker::ContextBroker::new(policy_version.clone())),
            policy_version,
        }
    }

    /// 评估导航意图（URL 解析 + 会话验证 → FfiDecision——fail-closed）。
    pub fn evaluate_navigation(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        // URL 解析（fail-closed：解析失败 → Deny）
        let parsed = crate::origin::try_parse_external(&raw_url);
        let (scheme, host) = match parsed {
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
            origin: format!("{scheme}://{host}"),
            method: "GET".into(),
            canonical_parameters: String::new(),
            scope: scope.clone(),
            expires_at,
            nonce,
            policy_version: self.policy_version.clone(),
            explanation: format!("allowed origin {scheme}://{host} — scheme {scheme}, host {host}"),
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
        FfiDecision::from(decision)
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
        match self.inner.lock() {
            Ok(mut g) => {
                g.destroy_session(&session_id);
                true
            }
            Err(_) => false,
        }
    }

    /// 在副作用执行点校验并消费授权动作，拒绝失效或已使用的 nonce。
    pub fn consume_authorized_action(&self, action: FfiAuthorizedAction) -> FfiDecision {
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
        let decision = match self.inner.lock() {
            Ok(mut broker) => broker.validate_and_consume(&action),
            Err(_) => Decision::Deny(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        FfiDecision::from(decision)
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ffi_broker_allows_and_consumes_valid_session_action() {
        let broker = FfiBroker::new("1.0".into());
        assert!(broker.create_session("s1".into(), "t1".into(), 7, 60));
        let decision = broker.evaluate_navigation(
            "s1".into(),
            "t1".into(),
            7,
            "https://example.com/path?query=1".into(),
            "navigation".into(),
        );
        match decision {
            FfiDecision::Allow { action } => {
                assert_eq!(action.policy_version, "1.0");
                assert!(action.expires_at > 120);
                assert!(matches!(
                    broker.consume_authorized_action(action),
                    FfiDecision::Allow { .. }
                ));
            }
            _ => panic!("active matching session should produce an authorization"),
        }
    }

    #[test]
    fn ffi_broker_denies_unknown_session() {
        let broker = FfiBroker::new("1.0".into());
        assert!(matches!(
            broker.evaluate_navigation(
                "missing".into(),
                "t1".into(),
                7,
                "https://example.com".into(),
                "navigation".into(),
            ),
            FfiDecision::Deny { .. }
        ));
    }
}

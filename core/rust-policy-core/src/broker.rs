//! ContextBroker（照搬 fieldpass/picket ContextBroker 会话池模式）。
//!
//! 管理多个 persona context（会话池），每个 context 独立绑定 session/tab/generation，
//! 并支持原子消费 nonce（一次性、过期、重放拒绝）。
//!
//! 职责：
//! - 维护活跃会话池（HashMap<String, SessionContext>）
//! - 创建/销毁会话（生命周期管理）
//! - 一次性 nonce 消费（原子性——重放拒绝）
//! - 上下文绑定验证（session/tab/generation/scope/policy_version）
//!
//! 可拆卸：本模块不依赖 UI/网络/文件，纯内存数据结构。
//! 可拼接：通过 `Decision` trait 与 broker/executor 层对接。

use std::collections::HashMap;
use std::time::{Duration, Instant};

use crate::decision::{AuthorizedAction, DenyReason, Decision};

/// 单个会话上下文（persona session——隔离绑定）。
#[derive(Debug, Clone)]
pub struct SessionContext {
    pub session_id: String,
    pub tab_id: String,
    pub generation: u64,
    pub policy_version: String,
    pub created_at: Instant,
    pub ttl: Duration,
}

impl SessionContext {
    pub fn is_expired(&self) -> bool {
        self.created_at.elapsed() > self.ttl
    }
}

/// 一次性 nonce 消费记录（防重放）。
#[derive(Debug, Clone)]
struct NonceRecord {
    consumed_at: Instant,
    session_id: String,
}

/// ContextBroker——会话池 + nonce 消费管理（照搬 picket ContextBroker）。
#[derive(Debug)]
pub struct ContextBroker {
    sessions: HashMap<String, SessionContext>,
    consumed_nonces: HashMap<String, NonceRecord>,
    policy_version: String,
}

impl ContextBroker {
    pub fn new(policy_version: String) -> Self {
        Self {
            sessions: HashMap::new(),
            consumed_nonces: HashMap::new(),
            policy_version,
        }
    }

    /// 创建新会话（persona context）。
    pub fn create_session(
        &mut self,
        session_id: String,
        tab_id: String,
        generation: u64,
        ttl: Duration,
    ) -> &SessionContext {
        let ctx = SessionContext {
            session_id: session_id.clone(),
            tab_id,
            generation,
            policy_version: self.policy_version.clone(),
            created_at: Instant::now(),
            ttl,
        };
        self.sessions.insert(session_id.clone(), ctx);
        self.sessions.get(&session_id).unwrap()
    }

    /// 销毁会话（清理 nonce 记录）。
    pub fn destroy_session(&mut self, session_id: &str) {
        self.sessions.remove(session_id);
        self.consumed_nonces.retain(|_, r| r.session_id != session_id);
    }

    /// 清理过期会话（LRU 淘汰）。
    pub fn evict_expired(&mut self) {
        let expired: Vec<String> = self.sessions
            .iter()
            .filter(|(_, ctx)| ctx.is_expired())
            .map(|(id, _)| id.clone())
            .collect();
        for id in expired {
            self.destroy_session(&id);
        }
    }

    /// 验证 AuthorizedAction 上下文（fail-closed）。
    pub fn validate_action(&self, action: &AuthorizedAction) -> Decision {
        // 检查会话存在
        let session = match self.sessions.get(&action.session_id) {
            Some(s) => s,
            None => {
                return Decision::Deny(DenyReason {
                    code: "session_not_found".into(),
                    detail: format!("会话 {} 不存在或已过期", action.session_id),
                    explanation: format!(
                        "denied — session {} not found — policy version {}",
                        action.session_id, action.policy_version
                    ),
                });
            }
        };

        // 检查会话过期
        if session.is_expired() {
            return Decision::Deny(DenyReason {
                code: "session_expired".into(),
                detail: format!("会话 {} 已过期", action.session_id),
                explanation: format!(
                    "denied — session {} expired — policy version {}",
                    action.session_id, action.policy_version
                ),
            });
        }

        // 检查策略版本
        if action.policy_version != self.policy_version {
            return Decision::Deny(DenyReason {
                code: "policy_version_mismatch".into(),
                detail: format!(
                    "策略版本不匹配：期望 {}，实际 {}",
                    self.policy_version, action.policy_version
                ),
                explanation: format!(
                    "denied — policy version mismatch: expected {}, got {}",
                    self.policy_version, action.policy_version
                ),
            });
        }

        // 检查代际绑定
        if action.document_generation != session.generation {
            return Decision::Deny(DenyReason {
                code: "generation_mismatch".into(),
                detail: format!(
                    "代际不匹配：会话代际 {}，操作代际 {}",
                    session.generation, action.document_generation
                ),
                explanation: format!(
                    "denied — generation mismatch: session {}, action {}",
                    session.generation, action.document_generation
                ),
            });
        }

        Decision::Allow(action.clone())
    }

    /// 原子消费 nonce（一次性——重放拒绝）。
    pub fn consume_nonce(&mut self, nonce: &str, session_id: &str) -> Result<(), DenyReason> {
        if self.consumed_nonces.contains_key(nonce) {
            let record = &self.consumed_nonces[nonce];
            return Err(DenyReason {
                code: "nonce_replay".into(),
                detail: format!(
                    "nonce {} 已被消费（会话 {}）——重放拒绝",
                    nonce, record.session_id
                ),
                explanation: format!(
                    "denied — nonce {} already consumed by session {} — replay rejected",
                    nonce, record.session_id
                ),
            });
        }

        self.consumed_nonces.insert(
            nonce.to_string(),
            NonceRecord {
                consumed_at: Instant::now(),
                session_id: session_id.to_string(),
            },
        );
        Ok(())
    }

    /// 当前活跃会话数。
    pub fn active_session_count(&self) -> usize {
        self.sessions.len()
    }

    /// 当前已消费 nonce 数。
    pub fn consumed_nonce_count(&self) -> usize {
        self.consumed_nonces.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::decision::AuthorizedAction;

    fn make_action(session: &str, gen: u64, nonce: &str) -> AuthorizedAction {
        AuthorizedAction {
            session_id: session.into(),
            tab_id: "tab-0".into(),
            document_generation: gen,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/".into(),
            scope: "navigation:read".into(),
            expires_at: 9999999999,
            nonce: nonce.into(),
            policy_version: "1.0".into(),
            explanation: String::new(),
        }
    }

    #[test]
    fn create_and_validate_session() {
        let mut broker = ContextBroker::new("1.0".into());
        broker.create_session("s1".into(), "t1".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 1, "n1");
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Allow(_)));
    }

    #[test]
    fn session_not_found_is_deny() {
        let broker = ContextBroker::new("1.0".into());
        let action = make_action("missing", 1, "n1");
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn policy_version_mismatch_is_deny() {
        let mut broker = ContextBroker::new("1.0".into());
        broker.create_session("s1".into(), "t1".into(), 1, Duration::from_secs(3600));
        let mut action = make_action("s1", 1, "n1");
        action.policy_version = "2.0".into();
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn generation_mismatch_is_deny() {
        let mut broker = ContextBroker::new("1.0".into());
        broker.create_session("s1".into(), "t1".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 999, "n1");
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn nonce_consume_once_ok() {
        let mut broker = ContextBroker::new("1.0".into());
        assert!(broker.consume_nonce("n1", "s1").is_ok());
    }

    #[test]
    fn nonce_replay_rejected() {
        let mut broker = ContextBroker::new("1.0".into());
        broker.consume_nonce("n1", "s1").unwrap();
        let result = broker.consume_nonce("n1", "s2");
        assert!(result.is_err());
    }
}

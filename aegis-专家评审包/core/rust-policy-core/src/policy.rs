//! Policy（照搬 fieldpass/picket Policy fail-safe 升级模式）。
//!
//! 本地策略 + 远程策略客户端（Warden 远程服务），
//! 本地策略优先，远程降级时 fail-safe 升级（默认拒绝）。
//!
//! 职责：
//! - 本地策略评估（纯函数——无网络）
//! - 远程策略客户端（可选——降级时 fail-safe）
//! - fail-safe 升级（本地策略未知时默认拒绝）
//!
//! 可拆卸：本模块不依赖 UI/网络（远程客户端可选）。
//! 可拼接：通过 `Decision` trait 与 broker 层对接。

use crate::action_policy::{ActionPolicy, PolicyDecision, RuleEffect};
use crate::decision::{AuthorizedAction, Decision, DenyReason};

/// 策略评估结果（本地 or 远程）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicySource {
    /// 本地策略（纯函数——无网络）。
    Local,
    /// 远程策略（Warden 服务——可选）。
    Remote,
    /// fail-safe 默认拒绝（无策略可用）。
    FailSafe,
}

/// 策略决策（来源 + 决策）。
#[derive(Debug, Clone)]
pub struct PolicyVerdict {
    pub source: PolicySource,
    pub decision: Decision,
}

/// 本地策略接口（纯函数——无 I/O）。
pub trait LocalPolicy: Send + Sync {
    fn evaluate(&self, action: &str, context: &str) -> Option<Decision>;
}

/// 远程策略客户端接口（可选——网络调用）。
pub trait RemotePolicy: Send + Sync {
    fn evaluate(&self, action: &str, context: &str) -> Option<Decision>;
}

/// Policy 引擎——本地优先 + fail-safe 升级（照搬 picket Policy）。
pub struct PolicyEngine {
    local: Box<dyn LocalPolicy>,
    remote: Option<Box<dyn RemotePolicy>>,
}

impl PolicyEngine {
    pub fn new(local: Box<dyn LocalPolicy>, remote: Option<Box<dyn RemotePolicy>>) -> Self {
        Self { local, remote }
    }

    /// 评估策略（本地优先 → 远程降级 → fail-safe 默认拒绝）。
    pub fn evaluate(&self, action: &str, context: &str) -> PolicyVerdict {
        // 1. 本地策略优先
        if let Some(decision) = self.local.evaluate(action, context) {
            return PolicyVerdict {
                source: PolicySource::Local,
                decision,
            };
        }

        // 2. 远程策略降级
        if let Some(remote) = &self.remote {
            if let Some(decision) = remote.evaluate(action, context) {
                return PolicyVerdict {
                    source: PolicySource::Remote,
                    decision,
                };
            }
        }

        // 3. fail-safe 默认拒绝
        PolicyVerdict {
            source: PolicySource::FailSafe,
            decision: Decision::Deny(DenyReason {
                code: "fail_safe".into(),
                detail: "本地策略未知 + 远程策略不可用——默认拒绝".into(),
                explanation: format!(
                    "denied — fail-safe: no local or remote policy matched for action '{}' — default deny",
                    action
                ),
            }),
        }
    }
}

impl Default for PolicyEngine {
    fn default() -> Self {
        Self::new(Box::new(DefaultLocalPolicy::new()), None)
    }
}

/// 默认本地策略——包装 ActionPolicy（fail-closed：默认拒绝）。
pub struct DefaultLocalPolicy {
    inner: ActionPolicy,
}

impl DefaultLocalPolicy {
    pub fn new() -> Self {
        Self {
            inner: ActionPolicy::new(RuleEffect::Deny),
        }
    }

    pub fn with_action_policy(policy: ActionPolicy) -> Self {
        Self { inner: policy }
    }

    pub fn action_policy(&mut self) -> &mut ActionPolicy {
        &mut self.inner
    }
}

impl Default for DefaultLocalPolicy {
    fn default() -> Self {
        Self::new()
    }
}

impl LocalPolicy for DefaultLocalPolicy {
    fn evaluate(&self, action: &str, context: &str) -> Option<Decision> {
        // 仅当显式规则匹配时返回 Some；无匹配返回 None → 上层走 FailSafe
        let decision = self.inner.evaluate_opt(action, context)?;
        Some(match decision {
            PolicyDecision::Allow(explanation) => Decision::Allow(AuthorizedAction {
                session_id: String::new(),
                tab_id: String::new(),
                document_generation: 0,
                origin: context.to_string(),
                method: String::new(),
                canonical_parameters: String::new(),
                scope: action.to_string(),
                expires_at: 0,
                nonce: String::new(),
                policy_version: String::new(),
                explanation,
            }),
            PolicyDecision::Deny(explanation) => Decision::Deny(DenyReason {
                code: "policy_denied".into(),
                detail: explanation.clone(),
                explanation,
            }),
            PolicyDecision::Ask(_explanation) => {
                Decision::RequireConfirmation(crate::decision::ApprovalRequest {
                    origin: context.to_string(),
                    method: String::new(),
                    path: String::new(),
                    scope: action.to_string(),
                    expires_at: 0,
                    nonce: String::new(),
                })
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::decision::AuthorizedAction;

    struct MockLocalPolicy {
        allow_action: String,
    }

    impl LocalPolicy for MockLocalPolicy {
        fn evaluate(&self, action: &str, _context: &str) -> Option<Decision> {
            if action == self.allow_action {
                Some(Decision::Allow(AuthorizedAction {
                    session_id: "test".into(),
                    tab_id: "test".into(),
                    document_generation: 0,
                    origin: "https://test.com".into(),
                    method: "GET".into(),
                    canonical_parameters: "/".into(),
                    scope: "test".into(),
                    expires_at: 9999999999,
                    nonce: "test".into(),
                    policy_version: "1.0".into(),
                    explanation: "test allow".into(),
                }))
            } else {
                None
            }
        }
    }

    #[test]
    fn local_policy_match_returns_allow() {
        let engine = PolicyEngine::new(
            Box::new(MockLocalPolicy {
                allow_action: "read".into(),
            }),
            None,
        );
        let result = engine.evaluate("read", "ctx");
        assert_eq!(result.source, PolicySource::Local);
        assert!(matches!(result.decision, Decision::Allow(_)));
    }

    #[test]
    fn no_match_fail_safe_deny() {
        let engine = PolicyEngine::new(
            Box::new(MockLocalPolicy {
                allow_action: "read".into(),
            }),
            None,
        );
        let result = engine.evaluate("write", "ctx");
        assert_eq!(result.source, PolicySource::FailSafe);
        assert!(matches!(result.decision, Decision::Deny(_)));
    }

    #[test]
    fn default_policy_engine_uses_default_local_policy() {
        let engine = PolicyEngine::default();
        let result = engine.evaluate("any_action", "ctx");
        assert_eq!(result.source, PolicySource::FailSafe);
        assert!(matches!(result.decision, Decision::Deny(_)));
    }

    #[test]
    fn default_local_policy_no_rules_returns_none() {
        let policy = DefaultLocalPolicy::new();
        let result = policy.evaluate("navigation:read", "https://example.com");
        // 无规则匹配 → None → 上层引擎走 FailSafe
        assert!(result.is_none());
    }

    #[test]
    fn default_local_policy_with_explicit_deny_rule() {
        use crate::action_policy::{PolicyRule, RuleEffect};
        let mut policy = DefaultLocalPolicy::new();
        policy.inner.add_rule(PolicyRule {
            name: "deny_nav".into(),
            action_pattern: "navigation:*".into(),
            condition: None,
            effect: RuleEffect::Deny,
            priority: 0,
        });
        let result = policy.evaluate("navigation:read", "https://example.com");
        assert!(matches!(result, Some(Decision::Deny(_))));
    }
}

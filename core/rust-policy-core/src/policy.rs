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
use crate::decision::{Decision, DenyReason};

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
///
/// RS-092：返回 `None` 表示「本地无匹配」——上层引擎据此走远程降级
/// 或 fail-safe 默认拒绝；`Some` 表示显式裁决（Allow/Deny/确认）。
pub trait LocalPolicy: Send + Sync {
    /// 评估动作；无匹配返回 None（不等于 Deny）。
    fn evaluate(&self, action: &str, context: &str) -> Option<Decision>;
}

/// 远程策略客户端接口（可选——网络调用）。
///
/// RS-092：与 LocalPolicy 同形但语义不同——实现方负责网络 I/O 与
/// 超时；返回 None 时引擎降级到 fail-safe（绝不本地兜底放行）。
pub trait RemotePolicy: Send + Sync {
    /// 远程评估动作；不可用/超时返回 None。
    fn evaluate(&self, action: &str, context: &str) -> Option<Decision>;
}

/// Policy 引擎——本地优先 + fail-safe 升级（照搬 picket Policy）。
pub struct PolicyEngine {
    local: Box<dyn LocalPolicy>,
    remote: Option<Box<dyn RemotePolicy>>,
}

impl PolicyEngine {
    /// 创建引擎：`local` 必选（纯函数基座），`remote` 可选（降级通道）。
    ///
    /// RS-091：评估序为 local → remote → fail-safe 默认拒绝，
    /// 任一环节命中即短路。
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
    /// 创建默认本地策略：包装 fail-closed 的 ActionPolicy（默认拒绝）。
    ///
    /// RS-091：无规则时 evaluate 返回 None（上层走 fail-safe），
    /// 显式 Deny 规则命中时返回 Deny。
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
            PolicyDecision::Allow(_explanation) => {
                // RS-029（审计 2026-09-24）：本地规则 Allow 映射出的
                // AuthorizedAction 带空凭据（session/nonce 空、expires_at=0）
                // ——下游 validate_action 必以 action_expired/session_not_found
                // 拒绝，Allow 永远是死路。升级为 RequireConfirmation：由宿主
                // 走交互审批铸造真实 nonce（fail-closed，绝不放行空凭据授权）
                Decision::RequireConfirmation(crate::decision::ApprovalRequest {
                    origin: context.to_string(),
                    method: String::new(),
                    path: String::new(),
                    scope: action.to_string(),
                    expires_at: 0,
                    nonce: String::new(),
                })
            }
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

    struct MockRemotePolicy {
        decision: Option<Decision>,
    }

    impl RemotePolicy for MockRemotePolicy {
        fn evaluate(&self, _action: &str, _context: &str) -> Option<Decision> {
            self.decision.clone()
        }
    }

    #[test]
    fn remote_downgrade_allows_when_local_no_match() {
        // RS-041 用例 1：本地无匹配 → 远程 Allow 决策被采纳，来源标记 Remote
        let engine = PolicyEngine::new(
            Box::new(MockLocalPolicy {
                allow_action: "read".into(),
            }),
            Some(Box::new(MockRemotePolicy {
                decision: Some(Decision::Allow(AuthorizedAction {
                    session_id: "remote".into(),
                    tab_id: "remote".into(),
                    document_generation: 0,
                    origin: "https://remote.com".into(),
                    method: "GET".into(),
                    canonical_parameters: "/".into(),
                    scope: "write".into(),
                    expires_at: 9999999999,
                    nonce: "remote-nonce".into(),
                    policy_version: "1.0".into(),
                    explanation: "remote allow".into(),
                })),
            })),
        );
        let result = engine.evaluate("write", "ctx");
        assert_eq!(result.source, PolicySource::Remote);
        assert!(matches!(result.decision, Decision::Allow(_)));
    }

    #[test]
    fn remote_downgrade_denies_propagates_deny() {
        // RS-041 用例 2：远程 Deny 决策原样传播（不得降级为 FailSafe 或放宽）
        let engine = PolicyEngine::new(
            Box::new(MockLocalPolicy {
                allow_action: "read".into(),
            }),
            Some(Box::new(MockRemotePolicy {
                decision: Some(Decision::Deny(DenyReason {
                    code: "remote_denied".into(),
                    detail: "远程策略拒绝".into(),
                    explanation: "denied — remote policy".into(),
                })),
            })),
        );
        let result = engine.evaluate("write", "ctx");
        assert_eq!(result.source, PolicySource::Remote);
        match result.decision {
            Decision::Deny(reason) => assert_eq!(reason.code, "remote_denied"),
            other => panic!("期望远程 Deny，实际 {other:?}"),
        }
    }

    #[test]
    fn remote_unavailable_falls_through_to_fail_safe() {
        // RS-041 用例 3：远程客户端存在但返回 None（不可用）→ fail-safe 默认拒绝
        let engine = PolicyEngine::new(
            Box::new(MockLocalPolicy {
                allow_action: "read".into(),
            }),
            Some(Box::new(MockRemotePolicy { decision: None })),
        );
        let result = engine.evaluate("write", "ctx");
        assert_eq!(result.source, PolicySource::FailSafe);
        assert!(matches!(result.decision, Decision::Deny(_)));
        match result.decision {
            Decision::Deny(reason) => assert_eq!(reason.code, "fail_safe"),
            other => panic!("期望 fail_safe 拒绝，实际 {other:?}"),
        }
    }

    #[test]
    fn local_priority_over_remote() {
        // RS-041 补充：本地命中时远程不得被咨询（本地优先序锁定）
        let engine = PolicyEngine::new(
            Box::new(MockLocalPolicy {
                allow_action: "read".into(),
            }),
            Some(Box::new(MockRemotePolicy {
                decision: Some(Decision::Deny(DenyReason {
                    code: "remote_denied".into(),
                    detail: String::new(),
                    explanation: String::new(),
                })),
            })),
        );
        let result = engine.evaluate("read", "ctx");
        assert_eq!(result.source, PolicySource::Local);
        assert!(matches!(result.decision, Decision::Allow(_)));
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

    #[test]
    fn local_allow_rule_upgrades_to_confirmation_not_empty_credentials() {
        // RS-029 回归：本地 Allow 规则不得映射空凭据 AuthorizedAction
        //（session/nonce 空 + expires_at=0 → 下游必拒的死路授权）——
        // 必须升级为 RequireConfirmation 交宿主铸造真实 nonce
        use crate::action_policy::{PolicyRule, RuleEffect};
        let mut policy = DefaultLocalPolicy::new();
        policy.inner.add_rule(PolicyRule {
            name: "allow_read".into(),
            action_pattern: "navigation:*".into(),
            condition: None,
            effect: RuleEffect::Allow,
            priority: 0,
        });
        let result = policy.evaluate("navigation:read", "https://example.com");
        match result {
            Some(Decision::RequireConfirmation(_)) => {}
            other => panic!("Allow 规则必须升级为 RequireConfirmation，实际 {other:?}"),
        }
    }

    #[test]
    fn local_ask_rule_maps_to_confirmation() {
        // RS-093：Ask 规则映射 RequireConfirmation——高风险动作交宿主
        // 交互审批（origin/scope 透传，nonce/expires 留空由宿主铸造）
        use crate::action_policy::{PolicyRule, RuleEffect};
        let mut policy = DefaultLocalPolicy::new();
        policy.inner.add_rule(PolicyRule {
            name: "ask_write".into(),
            action_pattern: "clipboard:write".into(),
            condition: None,
            effect: RuleEffect::Ask,
            priority: 0,
        });
        let result = policy.evaluate("clipboard:write", "https://example.com");
        match result {
            Some(Decision::RequireConfirmation(req)) => {
                assert_eq!(req.origin, "https://example.com", "origin 透传");
                assert_eq!(req.scope, "clipboard:write", "scope 透传");
            }
            other => panic!("Ask 规则必须映射 RequireConfirmation，实际 {other:?}"),
        }
        // 对照：同策略下未匹配动作仍走 None（上层 fail-safe）
        assert!(
            policy
                .evaluate("navigation:read", "https://example.com")
                .is_none()
        );
    }

    // —— RS-154（审计 2026-09-25）：短路顺序计数 mock ——

    use std::sync::{Arc, Mutex};

    /// 计数本地策略：记录 evaluate 调用序，恒返回 None（走降级）。
    struct CountingLocalPolicy {
        calls: Arc<Mutex<Vec<&'static str>>>,
    }

    impl LocalPolicy for CountingLocalPolicy {
        fn evaluate(&self, _action: &str, _context: &str) -> Option<Decision> {
            self.calls.lock().expect("计数锁").push("local");
            None
        }
    }

    /// 计数远程策略：记录 evaluate 调用序，按注入决策返回。
    struct CountingRemotePolicy {
        calls: Arc<Mutex<Vec<&'static str>>>,
        decision: Option<Decision>,
    }

    impl RemotePolicy for CountingRemotePolicy {
        fn evaluate(&self, _action: &str, _context: &str) -> Option<Decision> {
            self.calls.lock().expect("计数锁").push("remote");
            self.decision.clone()
        }
    }

    #[test]
    fn evaluation_order_local_then_remote_then_failsafe() {
        // RS-154：评估序锁定——本地先于远程被咨询，两者都未命中才落
        // fail-safe（RS-091 口径）。此前只有来源断言，调用顺序零覆盖：
        // 若实现交换 local/remote 次序，现有测试不会失败
        let calls = Arc::new(Mutex::new(Vec::new()));
        let engine = PolicyEngine::new(
            Box::new(CountingLocalPolicy {
                calls: Arc::clone(&calls),
            }),
            Some(Box::new(CountingRemotePolicy {
                calls: Arc::clone(&calls),
                decision: None,
            })),
        );
        let result = engine.evaluate("anything", "ctx");
        assert_eq!(result.source, PolicySource::FailSafe);
        assert_eq!(
            *calls.lock().expect("计数锁"),
            vec!["local", "remote"],
            "评估序必须 local → remote（fail-safe 由两者未命中触发）"
        );
    }

    #[test]
    fn local_hit_short_circuits_remote_consultation() {
        // RS-154：本地显式裁决即短路——远程不得被咨询（少一次降级
        // 探测 = 少一次网络面暴露）。计数 mock 让「未咨询」可观测
        let calls = Arc::new(Mutex::new(Vec::new()));
        struct AllowAllLocal {
            calls: Arc<Mutex<Vec<&'static str>>>,
        }
        impl LocalPolicy for AllowAllLocal {
            fn evaluate(&self, _action: &str, _context: &str) -> Option<Decision> {
                self.calls.lock().expect("计数锁").push("local");
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
                    explanation: "short-circuit mock".into(),
                }))
            }
        }
        let engine = PolicyEngine::new(
            Box::new(AllowAllLocal {
                calls: Arc::clone(&calls),
            }),
            Some(Box::new(CountingRemotePolicy {
                calls: Arc::clone(&calls),
                decision: Some(Decision::Deny(DenyReason {
                    code: "remote_denied".into(),
                    detail: String::new(),
                    explanation: String::new(),
                })),
            })),
        );
        let result = engine.evaluate("read", "ctx");
        assert_eq!(result.source, PolicySource::Local);
        assert!(matches!(result.decision, Decision::Allow(_)));
        assert_eq!(
            *calls.lock().expect("计数锁"),
            vec!["local"],
            "本地命中后远程必须零咨询（短路）"
        );
    }
}

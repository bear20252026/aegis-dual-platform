//! AX-02（外部第三轮审计 2026-10-11 = H-7）：策略层与能力层接入 FFI 导航通路。
//!
//! 缺口本身是真的：`ContextBroker::evaluate`（broker.rs）跑三层
//! （policy → capability → 会话/nonce），而 FFI 的 `evaluate_navigation`  historically
//! 只跑第三层。但**照字面把它接上会拒掉每一次导航**，原因有两条实测事实：
//!
//! - 策略层：生产构造是 `PolicyEngine::default()`（空规则 + 无远程），
//!   `ActionPolicy::evaluate_opt` 在**没有任何规则匹配时返回 None**（`action_policy.rs:110`
//!   的 `let rule = best?;`，默认效果只作用于非 opt 的 `evaluate`）⇒ `PolicyEngine::evaluate`
//!   落到 `PolicySource::FailSafe` 的恒 Deny。把 FailSafe 当拒绝，就是全站拒绝。
//! - 能力层：`CapabilityRegistry::validate` 对**未注册**的 capability 一律拒绝
//!   （`capability.rs:156`），而生产注册表恒空 ⇒ 同样全拒。
//!
//! 所以口径是「**该层没有意见时不改裁决；一旦配置就生效，且它的 Deny 不可能被后面的
//! Allow 出口改回允许**」（单调加严）。这不是「接了个永远不响的钩子」：
//! `PolicyEngine::new` / `CapabilityRegistry::register` 一旦有宿主注入规则或能力，
//! 这里就是唯一的执行点——而在此之前两端谁都没有那个注入口（这正是它一直没被接上的原因，
//! 不是遗漏后被忽略）。测试把两侧都钉住：空配置逐字保持现结果，配置后必须改变结果。

use super::*;
use crate::policy::PolicySource;

impl ContextBroker {
    /// 会话验证之前的前置否决层。返回 `None` = 两层都没有意见（含未配置），
    /// 调用方继续按既有语义走；返回 `Some` = 该次导航的终局裁决。
    ///
    /// 只判不消费：nonce 与 capability 的推进仍由 `evaluate` 的第三层与 FFI 自己的
    /// 账本负责（FFI 通路的消费/复判语义由 `ffi_navigation_tests`/`consume_recheck_tests`
    /// 锁定，这里不动它们）。锁毒化不在此处发生（本方法拿 `&self`，由调用方持锁）。
    pub(crate) fn pre_layer_verdict(&self, action: &AuthorizedAction) -> Option<Decision> {
        // ===== 第 1 层：策略 =====
        let verdict = self.policy_engine.evaluate(&action.scope, &action.origin);
        if verdict.source != PolicySource::FailSafe {
            match verdict.decision {
                // 显式 Allow 规则仍交由下一层与账本处理；RS-029 已把本地 Allow 映射成
                // RequireConfirmation（空凭据的 Allow 是死路），所以这条分支实际只在
                // 远程策略给出 Allow 时到达。
                Decision::Allow(_) => {}
                other => return Some(other),
            }
        }

        // ===== 第 2 层：能力 =====
        if !self.capabilities.is_empty() {
            if let CapabilityResult::Denied(reason) =
                self.capabilities.validate(&action.scope, &action.origin)
            {
                return Some(Decision::Deny(DenyReason {
                    code: "capability_denied".into(),
                    detail: reason.clone(),
                    explanation: format!("denied — capability check failed: {reason}"),
                }));
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::super::*;
    use crate::action_policy::{ActionPolicy, PolicyRule, RuleEffect};
    use crate::capability::{Capability, CapabilityScope};
    use crate::policy::{DefaultLocalPolicy, PolicyEngine};

    fn action(scope: &str, origin: &str) -> AuthorizedAction {
        AuthorizedAction {
            session_id: "s-1".into(),
            tab_id: "t-1".into(),
            document_generation: 0,
            origin: origin.into(),
            method: "GET".into(),
            canonical_parameters: String::new(),
            scope: scope.into(),
            expires_at: u64::MAX,
            nonce: "n-1".into(),
            policy_version: "v1".into(),
            explanation: String::new(),
        }
    }

    fn broker_with(policy: PolicyEngine, capabilities: CapabilityRegistry) -> ContextBroker {
        ContextBroker::new("v1".into(), policy, capabilities)
    }

    fn rule(name: &str, pattern: &str, effect: RuleEffect) -> PolicyRule {
        PolicyRule {
            name: name.into(),
            action_pattern: pattern.into(),
            condition: None,
            effect,
            priority: 10,
        }
    }

    fn engine_with(rules: Vec<PolicyRule>) -> PolicyEngine {
        let mut policy = ActionPolicy::new(RuleEffect::Deny);
        for rule in rules {
            policy.add_rule(rule);
        }
        PolicyEngine::new(
            Box::new(DefaultLocalPolicy::with_action_policy(policy)),
            None,
        )
    }

    fn capability(name: &str, origin: &str) -> Capability {
        Capability::new(name, CapabilityScope::Execute, vec![origin.into()], None)
    }

    #[test]
    fn production_shape_is_inert_both_layers_unconfigured() {
        // 这一条是「出货行为零变更」的证明：生产构造（默认引擎 + 空注册表）下
        // 前置层必须给不出意见。反过来若有人把 FailSafe 当拒绝接进来，本用例即红。
        let broker = broker_with(PolicyEngine::default(), CapabilityRegistry::new());
        assert_eq!(
            None,
            broker.pre_layer_verdict(&action("navigation", "https://a.example"))
        );
    }

    #[test]
    fn explicit_deny_rule_becomes_a_final_denial() {
        let mut registry = CapabilityRegistry::new();
        registry.register(capability("navigation", "https://ok.example"));
        let broker = broker_with(
            engine_with(vec![rule("deny-net", "navigation", RuleEffect::Deny)]),
            registry,
        );
        match broker.pre_layer_verdict(&action("navigation", "https://ok.example")) {
            Some(Decision::Deny(reason)) => assert_eq!("policy_denied", reason.code),
            other => panic!("显式 Deny 规则必须产生终局拒绝，实得 {other:?}"),
        }
    }

    #[test]
    fn ask_rule_surfaces_require_confirmation_not_a_silent_allow() {
        let broker = broker_with(
            engine_with(vec![rule("ask-net", "navigation", RuleEffect::Ask)]),
            CapabilityRegistry::new(),
        );
        assert!(
            matches!(
                broker.pre_layer_verdict(&action("navigation", "https://a.example")),
                Some(Decision::RequireConfirmation(_))
            ),
            "Ask 规则不能在前置层被吞掉"
        );
    }

    #[test]
    fn configured_capability_registries_are_enforced() {
        // 注册表一旦非空就是白名单语义：未授予的 scope/origin 必须被拒。
        let mut registry = CapabilityRegistry::new();
        registry.register(capability("navigation", "https://ok.example"));
        let broker = broker_with(PolicyEngine::default(), registry);
        assert!(
            matches!(
                broker.pre_layer_verdict(&action("navigation", "https://evil.example")),
                Some(Decision::Deny(reason)) if reason.code == "capability_denied"
            ),
            "能力层配置后，白名单外的 origin 必须被拒"
        );
        assert_eq!(
            None,
            broker.pre_layer_verdict(&action("navigation", "https://ok.example")),
            "白名单内不该由能力层给意见（会话层负责）"
        );
    }

    #[test]
    fn deny_is_monotonic_a_later_allow_layer_cannot_reopen_it() {
        // 顺序判据：策略先给 Deny，能力层即便授予同一个 origin 也不能把它变回放行。
        let mut registry = CapabilityRegistry::new();
        registry.register(capability("navigation", "https://ok.example"));
        let broker = broker_with(
            engine_with(vec![rule("deny-net", "navigation", RuleEffect::Deny)]),
            registry,
        );
        assert!(matches!(
            broker.pre_layer_verdict(&action("navigation", "https://ok.example")),
            Some(Decision::Deny(_))
        ));
    }

    #[test]
    fn empty_registry_is_not_treated_as_a_deny_all_capability_gate() {
        // 与上一条配对的正向控制：空注册表 = 该层未配置，不是「什么都拒」——
        // validate 对未知 capability 恒 Denied，所以「非空」这一步判断本身是
        // 全站不可用与可用之间的分界，必须被钉住。
        let empty = CapabilityRegistry::new();
        assert!(empty.is_empty());
        assert!(matches!(
            empty.validate("navigation", "https://a.example"),
            CapabilityResult::Denied(_)
        ));
        let broker = broker_with(PolicyEngine::default(), CapabilityRegistry::new());
        assert_eq!(
            None,
            broker.pre_layer_verdict(&action("navigation", "https://a.example"))
        );
    }
}

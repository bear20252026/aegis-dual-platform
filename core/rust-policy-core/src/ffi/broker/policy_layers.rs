//! AX-02（外部第三轮审计 2026-10-11 = H-7）：FFI 导航通路的前置否决接入点。
//!
//! 判定本体在 `crate::broker::pre_layers`（那里同时讲清「为什么不能按字面直连」）。
//! 本文件只做两件事：把 `Decision` 映射成 `FfiDecision`，以及把
//! `RequireConfirmation` 交给既有的待审批登记链（复用同一个账本，不开第二条授权路径）。
//!
//! 这里另存一段拆分前写在 `ffi/broker.rs` 里的注记（黑名单注入的 Rust 侧单点在
//! `denylist.rs`——本文件所在的模块在 935 行零余量基线上，而 ⑨ 的档位入口与快照状态
//! 本就与黑名单口径是一体）：放在子模块里是因为它解释的是「为什么拆」，不是导航状态机。

use super::*;

impl FfiBroker {
    /// 会话验证之前的前置否决。`None` = 两层都没有意见，调用方按既有语义继续；
    /// `Some` = 该次导航的终局 `FfiDecision`。
    ///
    /// 锁毒化按既有口径处理成 Deny（`broker_lock`）——**不是**「拿不到锁就当没意见」，
    /// 那会把 fail-closed 悄悄换成 fail-open（与 `evaluate_navigation` 里 guard 分支同形）。
    pub(crate) fn pre_layer_gate(&self, action: &AuthorizedAction) -> Option<FfiDecision> {
        let verdict = match self.inner.lock() {
            Ok(guard) => guard.pre_layer_verdict(action),
            Err(_) => {
                return Some(ffi_deny(
                    "broker_lock",
                    "Broker 锁获取失败",
                    "denied — broker lock poisoned before the policy/capability layers",
                ));
            }
        }?;
        match verdict {
            Decision::Deny(reason) => Some(FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: reason.code,
                    detail: reason.detail,
                    explanation: reason.explanation,
                },
            }),
            // 复用既有确认登记链：nonce/账本/待审批表都只有一条路径，不开第二份。
            Decision::RequireConfirmation(_) => {
                Some(self.register_pending_approval(action.clone()))
            }
            Decision::Allow(_) => None,
        }
    }
}

#[cfg(test)]
impl FfiBroker {
    /// 测试注入构造器：把配好规则/能力的 `ContextBroker` 装进真实 FFI 通路。
    /// 没有它，「配置后确实生效」只能测到 `pre_layer_verdict`（核心侧），测不到
    /// 本文件的映射与出口顺序——那正是审计担心的那段。
    pub(crate) fn with_context_broker_for_tests(broker: crate::broker::ContextBroker) -> Self {
        Self {
            inner: std::sync::Mutex::new(broker),
            issued_actions: std::sync::Mutex::new(HashMap::new()),
            pending_navigation_approvals: std::sync::Mutex::new(HashMap::new()),
            deny_hosts: denylist::HostDenylist::default(),
            policy_version: "v1".into(),
            action_expiry_seconds: ACTION_EXPIRY_SECONDS,
            max_issued_actions: MAX_ISSUED_ACTIONS,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::action_policy::{ActionPolicy, PolicyRule, RuleEffect};
    use crate::broker::ContextBroker;
    use crate::capability::CapabilityRegistry;
    use crate::policy::{DefaultLocalPolicy, PolicyEngine};

    fn navigate(broker: &FfiBroker) -> FfiDecision {
        broker.evaluate_navigation(
            "s-1".into(),
            "t-1".into(),
            0,
            "https://example.com/x".into(),
            "navigation".into(),
        )
    }

    fn engine_with(effect: RuleEffect) -> PolicyEngine {
        let mut policy = ActionPolicy::new(RuleEffect::Deny);
        policy.add_rule(PolicyRule {
            name: "probe".into(),
            action_pattern: "navigation".into(),
            condition: None,
            effect,
            priority: 10,
        });
        PolicyEngine::new(
            Box::new(DefaultLocalPolicy::with_action_policy(policy)),
            None,
        )
    }

    /// 生产构造（默认引擎 + 空注册表）下，前置层必须**给不出意见**：结果完全由
    /// 既有通路决定。这里用「未建会话」这个必然失败点当探针——它证明的是
    /// 「拒绝码来自会话层而不是来自策略/能力层」，比拿一条 Allow 断言更严：
    /// 若有人把 FailSafe 当拒绝直连进来，第一个红的就是它。
    #[test]
    fn unconfigured_layers_do_not_shadow_the_existing_decision_path() {
        match navigate(&FfiBroker::new("v1".into())) {
            FfiDecision::Deny { reason } => assert_eq!(
                "session_not_found", reason.code,
                "出货构造下前置层不该抢先给意见（实得 {}）",
                reason.code
            ),
            other => panic!("未建会话应当是会话层拒绝，实得 {other:?}"),
        }
    }

    /// 前置层的 Deny 是终局的，并且**排在会话验证之前**：同一个未建会话的入参，
    /// 配置了 deny 规则后拿到的就是 policy_denied 而不是 session_not_found。
    /// 这条同时否掉两种接错法：放在 Allow 出口之后（会被会话结果覆盖）、
    /// 以及「策略拒绝但端侧还能继续走」。
    #[test]
    fn configured_deny_rule_reaches_the_ffi_caller_as_a_final_denial() {
        let broker = FfiBroker::with_context_broker_for_tests(ContextBroker::new(
            "v1".into(),
            engine_with(RuleEffect::Deny),
            CapabilityRegistry::new(),
        ));
        match navigate(&broker) {
            FfiDecision::Deny { reason } => {
                assert_eq!("policy_denied", reason.code);
                assert!(
                    reason.detail.contains("deny rule 'probe'"),
                    "detail 必须带着命中的规则名，否则线上无法归因，实得 {}",
                    reason.detail
                );
            }
            other => panic!("策略 Deny 必须以 Deny 出 FFI，实得 {other:?}"),
        }
    }

    #[test]
    fn configured_ask_rule_becomes_the_existing_confirmation_flow_not_a_second_path() {
        // Ask 必须走既有的待审批登记链（返回带 nonce 的 RequireConfirmation），
        // 而不是另开一条「挂起等批准」的路——那条会有第二份账。
        let broker = FfiBroker::with_context_broker_for_tests(ContextBroker::new(
            "v1".into(),
            engine_with(RuleEffect::Ask),
            CapabilityRegistry::new(),
        ));
        assert!(
            matches!(navigate(&broker), FfiDecision::RequireConfirmation { .. }),
            "Ask 规则必须转进既有确认链，实得 {:?}",
            navigate(&broker)
        );
    }
}

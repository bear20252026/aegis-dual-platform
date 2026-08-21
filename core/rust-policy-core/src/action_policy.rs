//! ActionPolicy（照搬 vercel-labs/agent-browser ActionPolicy 策略检查）。
//!
//! 对每个 agent 动作执行策略检查（允许/拒绝/确认），
//! 决策路径：CLI输入 → JSON序列化 → Schema验证 → 命令路由 → 策略强制 + 执行。
//!
//! 职责：
//! - 策略定义（action + condition → decision）
//! - 策略匹配（精确匹配 + glob 模式）
//! - 策略评估（deny > ask > allow 优先级）
//! - 审计日志（每次决策记录 explanation）
//!
//! 可拆卸：本模块不依赖 UI/网络/文件。
//! 可拼接：通过 Decision trait 与 broker/executor 层对接。

use crate::decision::{AuthorizedAction, Decision, DenyReason};
use crate::matcher::glob_match;

/// 策略规则（action + condition → decision）。
#[derive(Debug, Clone)]
pub struct PolicyRule {
    pub name: String,
    pub action_pattern: String,
    pub condition: Option<String>,
    pub effect: RuleEffect,
    pub priority: u8,
}

/// 规则效果（deny > ask > allow）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RuleEffect {
    Allow,
    Deny,
    Ask,
}

impl RuleEffect {
    pub fn restrictiveness(&self) -> u8 {
        match self {
            Self::Deny => 2,
            Self::Ask => 1,
            Self::Allow => 0,
        }
    }
}

/// ActionPolicy——策略检查器（照搬 agent-browser ActionPolicy）。
pub struct ActionPolicy {
    rules: Vec<PolicyRule>,
    default_effect: RuleEffect,
}

impl ActionPolicy {
    pub fn new(default_effect: RuleEffect) -> Self {
        Self {
            rules: Vec::new(),
            default_effect,
        }
    }

    /// 添加策略规则。
    pub fn add_rule(&mut self, rule: PolicyRule) {
        self.rules.push(rule);
    }

    /// 评估动作（deny > ask > allow 优先级——DenyOverrides 模式）。
    pub fn evaluate(&self, action: &str, context: &str) -> PolicyDecision {
        let matches: Vec<&PolicyRule> = self
            .rules
            .iter()
            .filter(|r| {
                glob_match(&r.action_pattern, action, false)
                    && r.condition
                        .as_ref()
                        .map_or(true, |c| context.contains(c.as_str()))
            })
            .collect();

        // DenyOverrides：deny > ask > allow
        if let Some(top) = matches.iter().map(|r| r.effect.restrictiveness()).max() {
            let rule = matches
                .iter()
                .find(|r| r.effect.restrictiveness() == top)
                .unwrap();

            return match &rule.effect {
                RuleEffect::Deny => PolicyDecision::Deny(format!(
                    "deny rule '{}' matched action '{}' — {}",
                    rule.name, action, rule.action_pattern
                )),
                RuleEffect::Ask => PolicyDecision::Ask(format!(
                    "ask rule '{}' matched action '{}' — requires confirmation",
                    rule.name, action
                )),
                RuleEffect::Allow => PolicyDecision::Allow(format!(
                    "allow rule '{}' matched action '{}'",
                    rule.name, action
                )),
            };
        }

        // 无匹配——默认效果
        match &self.default_effect {
            RuleEffect::Deny => PolicyDecision::Deny("no rule matched — default deny".into()),
            RuleEffect::Ask => PolicyDecision::Ask("no rule matched — default ask".into()),
            RuleEffect::Allow => PolicyDecision::Allow("no rule matched — default allow".into()),
        }
    }
}

/// 策略决策结果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyDecision {
    Allow(String),
    Deny(String),
    Ask(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_rule(name: &str, pattern: &str, effect: RuleEffect) -> PolicyRule {
        PolicyRule {
            name: name.into(),
            action_pattern: pattern.into(),
            condition: None,
            effect,
            priority: 0,
        }
    }

    #[test]
    fn deny_overrides_allow() {
        let mut policy = ActionPolicy::new(RuleEffect::Allow);
        policy.add_rule(make_rule("allow_read", "read*", RuleEffect::Allow));
        policy.add_rule(make_rule("deny_secrets", "read*secret*", RuleEffect::Deny));
        assert!(matches!(
            policy.evaluate("read_secret", "ctx"),
            PolicyDecision::Deny(_)
        ));
    }

    #[test]
    fn no_match_default_deny() {
        let policy = ActionPolicy::new(RuleEffect::Deny);
        assert!(matches!(
            policy.evaluate("anything", "ctx"),
            PolicyDecision::Deny(_)
        ));
    }

    #[test]
    fn ask_takes_priority_over_allow() {
        let mut policy = ActionPolicy::new(RuleEffect::Allow);
        policy.add_rule(make_rule("allow", "write*", RuleEffect::Allow));
        policy.add_rule(make_rule("ask", "write*config*", RuleEffect::Ask));
        assert!(matches!(
            policy.evaluate("write_config", "ctx"),
            PolicyDecision::Ask(_)
        ));
    }
}

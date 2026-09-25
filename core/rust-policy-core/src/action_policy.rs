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
        match self.evaluate_opt(action, context) {
            Some(decision) => decision,
            None => match &self.default_effect {
                RuleEffect::Deny => PolicyDecision::Deny("no rule matched — default deny".into()),
                RuleEffect::Ask => PolicyDecision::Ask("no rule matched — default ask".into()),
                RuleEffect::Allow => {
                    PolicyDecision::Allow("no rule matched — default allow".into())
                }
            },
        }
    }

    /// 评估动作（仅当有规则匹配时返回 Some，否则 None）。
    /// 用于让上层策略引擎区分「显式匹配」与「无匹配走 fail-safe」。
    ///
    /// RS-095/096（审计 2026-09-25）：单趟裁决——此前先 collect 匹配
    /// Vec（每次评估分配）再 map+max+fold+unwrap 三趟选取；现一次遍历
    /// 以 (restrictiveness, priority) 字典序选优，无 unwrap、无中间分配。
    /// 同分保持先注册者（首胜——确定性）。
    pub fn evaluate_opt(&self, action: &str, context: &str) -> Option<PolicyDecision> {
        let mut best: Option<&PolicyRule> = None;
        for r in &self.rules {
            if !(glob_match(&r.action_pattern, action, false)
                && r.condition
                    .as_ref()
                    .is_none_or(|c| context_contains_token(context, c.as_str())))
            {
                continue;
            }
            best = Some(match best {
                None => r,
                Some(cur) => {
                    // DenyOverrides：deny > ask > allow；同效果内 priority
                    // 降序；字典序严格更大才替换——同分保首（RS-030）
                    if (r.effect.restrictiveness(), r.priority)
                        > (cur.effect.restrictiveness(), cur.priority)
                    {
                        r
                    } else {
                        cur
                    }
                }
            });
        }
        let rule = best?;

        Some(match &rule.effect {
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
        })
    }
}

/// 策略决策结果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyDecision {
    Allow(String),
    Deny(String),
    Ask(String),
}

/// 条件命中判定：条件串须出现在 token 边界（起点/`/`/`?`/`&`/`=`/`,`/空白之后）。
/// 此前裸 contains——条件 "example.com" 被 "https://evil.com/?x=example.com" 命中。
fn context_contains_token(context: &str, token: &str) -> bool {
    if token.is_empty() {
        return false;
    }
    let ctx = context.as_bytes();
    let tok = token.as_bytes();
    let mut from = 0;
    while let Some(pos) = context[from..].find(token) {
        let abs = from + pos;
        let before_ok = abs == 0
            || matches!(
                ctx[abs - 1],
                b'/' | b'?' | b'&' | b'=' | b',' | b' ' | b'\t' | b'\n' | b'\r'
            );
        let end = abs + tok.len();
        let after_ok = end == ctx.len()
            || matches!(
                ctx[end],
                b'/' | b'?' | b'&' | b'=' | b',' | b' ' | b'\t' | b'\n' | b'\r' | b':'
            );
        if before_ok && after_ok {
            return true;
        }
        // 推进到下一个 UTF-8 字符边界——abs+1 可落在多字节字符中间，
        // 下轮 context[from..] 切片即 panic（byte index not on char boundary）
        from = abs + 1;
        while from < context.len() && !context.is_char_boundary(from) {
            from += 1;
        }
        if from >= context.len() {
            break;
        }
    }
    false
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

    #[test]
    fn context_contains_token_multibyte_no_panic() {
        // RS-004 回归：多字节 UTF-8 续扫不得 panic（byte index not on char
        // boundary）。条件判定仅对带 condition 的规则触发。
        let mut policy = ActionPolicy::new(RuleEffect::Deny);
        let mut rule = make_rule("deny_you", "read*", RuleEffect::Deny);
        rule.condition = Some("example.com".into());
        policy.add_rule(rule);
        // 多次出现多字节字符 + 伪边界场景——此前在此 panic
        let _ = policy.evaluate("read", "x你你y你z你example.com你");
        let _ = policy.evaluate("read", "你你你你你你你你");
        let _ = policy.evaluate("read", "emoji😀😀x😀read😀example.com");
    }

    // ===== RS-045：context_contains_token 直接单测（此前仅经规则间接覆盖）=====

    #[test]
    fn token_at_start_matches() {
        assert!(context_contains_token("example.com/page", "example.com"));
    }

    #[test]
    fn empty_token_never_matches() {
        assert!(!context_contains_token("anything", ""));
        assert!(!context_contains_token("", ""));
    }

    #[test]
    fn embedded_substring_without_boundary_rejected() {
        // 修复目标：裸 contains 时代 "example.com" 命中 "notexample.com"
        assert!(!context_contains_token(
            "https://notexample.com/",
            "example.com"
        ));
        // 中缀伪边界（参数值尾接）也不命中——前面是字母
        assert!(!context_contains_token(
            "https://evil.com/?x=notexample.com",
            "example.com"
        ));
    }

    #[test]
    fn token_after_separator_matches() {
        // ? & = / , 空白均为合法前置边界
        assert!(context_contains_token(
            "https://evil.com/?x=example.com",
            "example.com"
        ));
        assert!(context_contains_token(
            "https://evil.com/?a=1&example.com",
            "example.com"
        ));
        assert!(context_contains_token(
            "https://a.com/redirect/example.com",
            "example.com"
        ));
        assert!(context_contains_token(
            "allow example.com please",
            "example.com"
        ));
        assert!(context_contains_token("a,b,example.com", "example.com"));
    }

    #[test]
    fn token_before_port_separator_matches() {
        // after 边界允许 ':'——host:port 形态命中
        assert!(context_contains_token(
            "https://example.com:8443/x",
            "example.com"
        ));
    }

    #[test]
    fn token_followed_by_letter_rejected() {
        // 后接字母（非边界）不得命中
        assert!(!context_contains_token(
            "example.com.evil.net",
            "example.com"
        ));
    }

    #[test]
    fn multibyte_scan_finds_token_after_cjk_without_panic() {
        // RS-004 联动：多字节字符夹持下逐字符推进不 panic（byte index
        // not on char boundary）。CJK 字符本身不是边界——紧邻 CJK 的
        // token 不命中（边界语义锁定）；纯多字节输入同样安全返回 false。
        assert!(!context_contains_token("你example.com我", "example.com"));
        assert!(!context_contains_token(
            "x你你y你z你example.com你",
            "example.com"
        ));
        // 纯多字节无 token → false 且不 panic
        assert!(!context_contains_token("你你你你你", "example.com"));
        // CJK 之后经合法边界（/）仍能命中——多字节推进不破坏后续扫描
        assert!(context_contains_token("你/example.com", "example.com"));
    }

    #[test]
    fn crlf_tab_are_boundaries() {
        assert!(context_contains_token("line1\nexample.com", "example.com"));
        assert!(context_contains_token("col1\texample.com", "example.com"));
        assert!(context_contains_token("cr\rexample.com", "example.com"));
    }

    #[test]
    fn priority_breaks_ties_within_same_effect() {
        // RS-030 回归：同效果（restrictiveness 相同）时高 priority 胜出，
        // 同 priority 保持首个匹配（确定性）
        let mut policy = ActionPolicy::new(RuleEffect::Allow);
        let mut low = make_rule("low", "read*", RuleEffect::Allow);
        low.priority = 1;
        let mut high = make_rule("high", "read*", RuleEffect::Allow);
        high.priority = 9;
        policy.add_rule(low);
        policy.add_rule(high);
        match policy.evaluate("read_file", "ctx") {
            PolicyDecision::Allow(msg) => assert!(msg.contains("high"), "高优先级须胜出：{msg}"),
            other => panic!("期望 Allow，实际 {other:?}"),
        }
        // 同 priority → 首个匹配
        let mut policy2 = ActionPolicy::new(RuleEffect::Allow);
        policy2.add_rule(make_rule("first", "read*", RuleEffect::Allow));
        policy2.add_rule(make_rule("second", "read*", RuleEffect::Allow));
        match policy2.evaluate("read_file", "ctx") {
            PolicyDecision::Allow(msg) => assert!(msg.contains("first")),
            other => panic!("期望 Allow，实际 {other:?}"),
        }
    }

    // ===== RS-094 回归（审计 2026-09-25）：默认值/首胜/限制性 =====

    #[test]
    fn default_effect_all_three_variants() {
        // RS-094：default_effect 三态全部生效（此前仅测 Deny 路径）
        let allow = ActionPolicy::new(RuleEffect::Allow);
        assert!(matches!(
            allow.evaluate("anything", "ctx"),
            PolicyDecision::Allow(_)
        ));
        let ask = ActionPolicy::new(RuleEffect::Ask);
        assert!(matches!(
            ask.evaluate("anything", "ctx"),
            PolicyDecision::Ask(_)
        ));
        let deny = ActionPolicy::new(RuleEffect::Deny);
        assert!(matches!(
            deny.evaluate("anything", "ctx"),
            PolicyDecision::Deny(_)
        ));
    }

    #[test]
    fn first_match_wins_when_fully_tied() {
        // RS-094：restrictiveness 与 priority 全同分时首胜（单趟重构后
        // 语义必须与旧 fold 一致——确定性契约）
        let mut policy = ActionPolicy::new(RuleEffect::Deny);
        let mut a = make_rule("alpha", "act*", RuleEffect::Allow);
        a.priority = 5;
        let mut b = make_rule("beta", "act*", RuleEffect::Allow);
        b.priority = 5;
        policy.add_rule(a);
        policy.add_rule(b);
        match policy.evaluate("act", "ctx") {
            PolicyDecision::Allow(msg) => assert!(msg.contains("alpha"), "先注册者胜：{msg}"),
            other => panic!("期望 Allow，实际 {other:?}"),
        }
    }

    #[test]
    fn restrictiveness_ordering_is_deny_ask_allow() {
        // RS-094：限制性排序数值契约——Deny(2) > Ask(1) > Allow(0)
        assert_eq!(RuleEffect::Deny.restrictiveness(), 2);
        assert_eq!(RuleEffect::Ask.restrictiveness(), 1);
        assert_eq!(RuleEffect::Allow.restrictiveness(), 0);
        // deny > ask：deny 规则命中时 ask 不遮蔽
        let mut policy = ActionPolicy::new(RuleEffect::Allow);
        policy.add_rule(make_rule("ask_all", "*", RuleEffect::Ask));
        policy.add_rule(make_rule("deny_evil", "*evil*", RuleEffect::Deny));
        assert!(matches!(
            policy.evaluate("run_evil", "ctx"),
            PolicyDecision::Deny(_)
        ));
    }

    #[test]
    fn single_pass_no_intermediate_allocation_semantics_preserved() {
        // RS-095/096：单趟重构后 restrictiveness 跨档优先 + priority 同档
        // 降序的组合裁决保持（低优先级高 restriction 仍胜）
        let mut policy = ActionPolicy::new(RuleEffect::Allow);
        let mut high_pri_allow = make_rule("pri_allow", "act*", RuleEffect::Allow);
        high_pri_allow.priority = 255;
        policy.add_rule(high_pri_allow);
        policy.add_rule(make_rule("any_deny", "act*", RuleEffect::Deny));
        assert!(
            matches!(policy.evaluate("act", "ctx"), PolicyDecision::Deny(_)),
            "restrictiveness 跨档优先于 priority"
        );
    }
}

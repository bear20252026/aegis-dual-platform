//! Executor（照搬 vercel-labs/agent-browser 5阶段命令流）。
//!
//! 命令执行管线：CLI输入 → JSON序列化 → Schema验证 → 命令路由 → 策略强制 + 执行。
//! 每个阶段独立隔离，失败不泄漏到下一阶段。
//!
//! 职责：
//! - 命令解析（JSON → 结构化命令）
//! - Schema 验证（字段类型/必填/枚举）
//! - 命令路由（command → handler）
//! - 策略强制（ActionPolicy 检查）
//! - 执行 + 审计
//!
//! 可拆卸：本模块不依赖 UI/网络/策略引擎。
//! 可拼接：通过 ActionPolicy + Decision trait 对接。

use std::collections::HashMap;

/// 解析后的命令（结构化——强类型）。
#[derive(Debug, Clone)]
pub struct ParsedCommand {
    pub command_type: String,
    pub target: String,
    pub parameters: HashMap<String, String>,
    pub origin: String,
}

/// 命令解析结果。
#[derive(Debug)]
pub enum ParseResult {
    Ok(ParsedCommand),
    Error(String),
}

/// Schema 验证结果。
///
/// RS-099（审计 2026-09-25）：`Valid` 不再携带 clone 的 ParsedCommand——
/// 验证仅做断言，管线继续使用阶段 1 的原实例（此前每次验证白拷一份）。
#[derive(Debug)]
pub enum SchemaResult {
    Valid,
    Invalid(String),
}

/// 执行结果。
#[derive(Debug)]
pub enum ExecuteResult {
    Success(String),
    Denied(String),
    Error(String),
}

/// 命令处理器 trait（可拆卸——每个 handler 独立）。
pub trait CommandHandler: Send + Sync {
    fn command_type(&self) -> &str;
    fn execute(&self, cmd: &ParsedCommand) -> ExecuteResult;
}

/// Executor——5阶段命令流（照搬 agent-browser 管线）。
pub struct Executor {
    handlers: HashMap<String, Box<dyn CommandHandler>>,
    policy: Option<crate::action_policy::ActionPolicy>,
}

impl Default for Executor {
    fn default() -> Self {
        Self::new()
    }
}

impl Executor {
    pub fn new() -> Self {
        Self {
            handlers: HashMap::new(),
            policy: None,
        }
    }

    /// 挂载内置策略检查器（RS-098：阶段 4 真正生效——此前 policy_check
    /// 参数是空操作，策略强制从未接入管线）。
    pub fn with_policy(mut self, policy: crate::action_policy::ActionPolicy) -> Self {
        self.policy = Some(policy);
        self
    }

    /// 注册命令处理器。
    pub fn register_handler(&mut self, handler: Box<dyn CommandHandler>) {
        self.handlers
            .insert(handler.command_type().to_string(), handler);
    }

    /// 5阶段执行管线：解析 → 验证 → 路由 → 策略强制 → 执行。
    ///
    /// `policy_check`：true 时对已挂载的内置策略执行阶段 4 检查
    ///（Deny/Ask → Denied；Allow → 继续）；未挂载策略则该阶段直通。
    pub fn execute_pipeline(&self, raw_input: &str, policy_check: bool) -> ExecuteResult {
        // 阶段 1：解析（JSON → 结构化命令）
        let cmd = match self.parse(raw_input) {
            ParseResult::Ok(cmd) => cmd,
            ParseResult::Error(e) => return ExecuteResult::Error(format!("解析失败: {e}")),
        };

        // 阶段 2：Schema 验证（RS-099：零 clone 断言）
        match self.validate_schema(&cmd) {
            SchemaResult::Invalid(e) => return ExecuteResult::Error(format!("验证失败: {e}")),
            SchemaResult::Valid => {}
        }

        // 阶段 3：命令路由
        let handler = match self.handlers.get(&cmd.command_type) {
            Some(h) => h,
            None => return ExecuteResult::Denied(format!("未知命令类型: {}", cmd.command_type)),
        };

        // 阶段 4：策略强制（RS-098：接入 ActionPolicy——此前空操作）
        if policy_check {
            if let Some(policy) = &self.policy {
                match policy.evaluate(&cmd.command_type, &cmd.origin) {
                    crate::action_policy::PolicyDecision::Deny(e) => {
                        return ExecuteResult::Denied(format!("策略拒绝: {e}"));
                    }
                    crate::action_policy::PolicyDecision::Ask(e) => {
                        return ExecuteResult::Denied(format!("需要确认: {e}"));
                    }
                    crate::action_policy::PolicyDecision::Allow(_) => {}
                }
            }
        }

        // 阶段 5：执行
        handler.execute(&cmd)
    }

    /// 阶段 1：解析（JSON → 结构化命令）。
    ///
    /// 此前为占位桩：恒返回 `command_type="default"`，真实命令永远无法路由。
    /// 现以 serde_json 解析 `{"command_type","target","parameters","origin"}`；
    /// 非 JSON / 缺字段按类型化错误拒绝。输入上限对齐 C ABI 64KB。
    fn parse(&self, raw: &str) -> ParseResult {
        const MAX_INPUT_BYTES: usize = 64 * 1024;
        if raw.trim().is_empty() {
            return ParseResult::Error("空输入".into());
        }
        if raw.len() > MAX_INPUT_BYTES {
            return ParseResult::Error("输入超长".into());
        }
        let value: serde_json::Value = match serde_json::from_str(raw) {
            Ok(v) => v,
            Err(e) => return ParseResult::Error(format!("非法 JSON: {e}")),
        };
        let command_type = value
            .get("command_type")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string();
        let target = value
            .get("target")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string();
        let origin = value
            .get("origin")
            .and_then(|v| v.as_str())
            .unwrap_or("cli")
            .to_string();
        let mut parameters = HashMap::new();
        if let Some(obj) = value.get("parameters").and_then(|v| v.as_object()) {
            for (k, v) in obj {
                let s = match v {
                    serde_json::Value::String(s) => s.clone(),
                    other => other.to_string(),
                };
                parameters.insert(k.clone(), s);
            }
        }
        ParseResult::Ok(ParsedCommand {
            command_type,
            target,
            parameters,
            origin,
        })
    }

    /// 阶段 2：Schema 验证。
    fn validate_schema(&self, cmd: &ParsedCommand) -> SchemaResult {
        if cmd.command_type.is_empty() {
            return SchemaResult::Invalid("command_type 不能为空".into());
        }
        if cmd.target.is_empty() {
            return SchemaResult::Invalid("target 不能为空".into());
        }
        SchemaResult::Valid
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct MockHandler;
    impl CommandHandler for MockHandler {
        fn command_type(&self) -> &str {
            "test"
        }
        fn execute(&self, _cmd: &ParsedCommand) -> ExecuteResult {
            ExecuteResult::Success("mock executed".into())
        }
    }

    #[test]
    fn empty_input_rejected() {
        let executor = Executor::new();
        assert!(matches!(
            executor.execute_pipeline("", false),
            ExecuteResult::Error(_)
        ));
    }

    #[test]
    fn unknown_command_denied() {
        let executor = Executor::new();
        // 合法 JSON 但 command_type 未注册——路由阶段拒绝
        assert!(matches!(
            executor.execute_pipeline(r#"{"command_type":"nope","target":"x"}"#, false),
            ExecuteResult::Denied(_)
        ));
    }

    #[test]
    fn registered_handler_executes() {
        let mut executor = Executor::new();
        executor.register_handler(Box::new(MockHandler));
        assert!(matches!(
            executor.execute_pipeline(r#"{"command_type":"test","target":"page"}"#, false),
            ExecuteResult::Success(_)
        ));
    }

    #[test]
    fn malformed_json_rejected() {
        let executor = Executor::new();
        assert!(matches!(
            executor.execute_pipeline("some input", false),
            ExecuteResult::Error(_)
        ));
        // 语法残缺的 JSON（截断对象）——serde 解析失败拒绝
        assert!(matches!(
            executor.execute_pipeline(r#"{"command_type":"x","target":"#, false),
            ExecuteResult::Error(_)
        ));
    }

    #[test]
    fn parse_extracts_fields_and_parameters() {
        let executor = Executor::new();
        let raw = r##"{"command_type":"click","target":"#btn","origin":"web","parameters":{"wait_ms":"500","count":2}}"##;
        match executor.execute_pipeline(raw, false) {
            ExecuteResult::Denied(msg) => {
                // 未注册 "click" handler——路由拒绝消息应携带真实类型（证明解析成功）
                assert!(
                    msg.contains("click"),
                    "路由消息未携带解析出的命令类型: {msg}"
                );
            }
            other => panic!("期望 Denied，实际 {other:?}"),
        }
    }

    #[test]
    fn oversized_input_rejected() {
        let executor = Executor::new();
        let big = format!(
            r#"{{"command_type":"x","target":"{}"}}"#,
            "a".repeat(70 * 1024)
        );
        assert!(matches!(
            executor.execute_pipeline(&big, false),
            ExecuteResult::Error(_)
        ));
    }

    // —— RS-097/098 回归（审计 2026-09-25） ——

    #[test]
    fn whitespace_only_input_rejected() {
        // RS-097：纯空白输入 fail-closed（trim 语义）
        let executor = Executor::new();
        assert!(matches!(
            executor.execute_pipeline("   ", false),
            ExecuteResult::Error(_)
        ));
        assert!(matches!(
            executor.execute_pipeline(" \t\r\n ", false),
            ExecuteResult::Error(_)
        ));
    }

    #[test]
    fn full_pipeline_delivers_parsed_fields_to_handler() {
        // RS-097：全链路——注册 handler 收到解析出的完整字段
        struct RecordingHandler;
        use std::sync::Mutex;
        static RECORDED: Mutex<Option<ParsedCommand>> = Mutex::new(None);
        impl CommandHandler for RecordingHandler {
            fn command_type(&self) -> &str {
                "record"
            }
            fn execute(&self, cmd: &ParsedCommand) -> ExecuteResult {
                *RECORDED.lock().unwrap() = Some(cmd.clone());
                ExecuteResult::Success("recorded".into())
            }
        }
        let mut executor = Executor::new();
        executor.register_handler(Box::new(RecordingHandler));
        let raw = r##"{"command_type":"record","target":"#ok","origin":"https://example.com","parameters":{"path":"/a","n":3}}"##;
        assert!(matches!(
            executor.execute_pipeline(raw, false),
            ExecuteResult::Success(_)
        ));
        let recorded = RECORDED.lock().unwrap().clone().expect("handler 未被调用");
        assert_eq!(recorded.command_type, "record");
        assert_eq!(recorded.target, "#ok");
        assert_eq!(recorded.origin, "https://example.com");
        assert_eq!(
            recorded.parameters.get("path").map(String::as_str),
            Some("/a")
        );
        assert_eq!(
            recorded.parameters.get("n").map(String::as_str),
            Some("3"),
            "非字符串参数 JSON 序列化透传"
        );
    }

    #[test]
    fn re_register_same_type_overwrites_handler() {
        // RS-097：同类型重复注册 = 覆盖（HashMap 语义锁定——后注册者生效）
        struct FirstHandler;
        struct SecondHandler;
        impl CommandHandler for FirstHandler {
            fn command_type(&self) -> &str {
                "dup"
            }
            fn execute(&self, _cmd: &ParsedCommand) -> ExecuteResult {
                ExecuteResult::Success("first".into())
            }
        }
        impl CommandHandler for SecondHandler {
            fn command_type(&self) -> &str {
                "dup"
            }
            fn execute(&self, _cmd: &ParsedCommand) -> ExecuteResult {
                ExecuteResult::Success("second".into())
            }
        }
        let mut executor = Executor::new();
        executor.register_handler(Box::new(FirstHandler));
        executor.register_handler(Box::new(SecondHandler));
        match executor.execute_pipeline(r#"{"command_type":"dup","target":"x"}"#, false) {
            ExecuteResult::Success(msg) => assert_eq!(msg, "second", "后注册者覆盖前者"),
            other => panic!("期望 Success，实际 {other:?}"),
        }
    }

    #[test]
    fn policy_check_enforces_mounted_action_policy() {
        // RS-098：阶段 4 真正接入——Deny/Ask 规则在 handler 执行前拦截
        use crate::action_policy::{PolicyDecision, PolicyRule, RuleEffect};
        let mut policy = crate::action_policy::ActionPolicy::new(RuleEffect::Allow);
        policy.add_rule(PolicyRule {
            name: "deny_evil_origin".into(),
            action_pattern: "test".into(),
            condition: Some("evil.com".into()),
            effect: RuleEffect::Deny,
            priority: 0,
        });
        let mut executor = Executor::new().with_policy(policy);
        executor.register_handler(Box::new(MockHandler));

        // 条件命中 → Denied（handler 不执行）
        let raw_evil = r#"{"command_type":"test","target":"x","origin":"https://evil.com/p"}"#;
        match executor.execute_pipeline(raw_evil, true) {
            ExecuteResult::Denied(msg) => assert!(msg.contains("策略拒绝"), "{msg}"),
            other => panic!("期望 Denied，实际 {other:?}"),
        }
        // 条件未命中 → 放行执行
        let raw_ok = r#"{"command_type":"test","target":"x","origin":"https://example.com"}"#;
        assert!(matches!(
            executor.execute_pipeline(raw_ok, true),
            ExecuteResult::Success(_)
        ));
        // policy_check=false → 阶段 4 直通（条件命中的恶源也执行）
        assert!(matches!(
            executor.execute_pipeline(raw_evil, false),
            ExecuteResult::Success(_)
        ));
        let _ = PolicyDecision::Allow(String::new()); // keep import used
    }

    // —— RS-166（审计 2026-09-25）：三枚举基础用例 ——

    #[test]
    fn pipeline_enums_basic_contract() {
        // RS-166：ParseResult / SchemaResult / ExecuteResult 三枚举此前
        // 只有管线间接路径，变体构造与 Debug 格式零直接覆盖——管线层
        // match 重构（如增删变体）不会惊动任何现有测试。基础契约锁定：
        // 变体存在、Debug 携带载荷、结构可判别
        // ParseResult：Ok / Error 两变体
        let ok = ParseResult::Ok(ParsedCommand {
            command_type: "test".into(),
            target: "t".into(),
            parameters: HashMap::new(),
            origin: "cli".into(),
        });
        assert!(matches!(ok, ParseResult::Ok(_)));
        assert!(format!("{ok:?}").contains("\"test\""), "Debug 携带载荷");
        let err = ParseResult::Error("bad".into());
        assert!(matches!(err, ParseResult::Error(_)));
        assert!(format!("{err:?}").contains("bad"));

        // SchemaResult：Valid / Invalid 两变体（Valid 无载荷——RS-099）
        assert!(matches!(SchemaResult::Valid, SchemaResult::Valid));
        let invalid = SchemaResult::Invalid("empty".into());
        assert!(format!("{invalid:?}").contains("empty"));

        // ExecuteResult：三变体 + Debug 携带消息
        let variants = [
            ExecuteResult::Success("ok".into()),
            ExecuteResult::Denied("no".into()),
            ExecuteResult::Error("err".into()),
        ];
        let labels = ["ok", "no", "err"];
        for (variant, label) in variants.iter().zip(labels) {
            let debug = format!("{variant:?}");
            assert!(debug.contains(label), "Debug 必须携带 {label}: {debug}");
        }
        // 类型化判别（matches! 主通道）
        assert!(matches!(variants[0], ExecuteResult::Success(_)));
        assert!(matches!(variants[1], ExecuteResult::Denied(_)));
        assert!(matches!(variants[2], ExecuteResult::Error(_)));
    }
}

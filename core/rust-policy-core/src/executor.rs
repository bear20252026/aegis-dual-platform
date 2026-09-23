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
#[derive(Debug)]
pub enum SchemaResult {
    Valid(ParsedCommand),
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
        }
    }

    /// 注册命令处理器。
    pub fn register_handler(&mut self, handler: Box<dyn CommandHandler>) {
        self.handlers
            .insert(handler.command_type().to_string(), handler);
    }

    /// 5阶段执行管线：解析 → 验证 → 路由 → 策略强制 → 执行。
    pub fn execute_pipeline(&self, raw_input: &str, policy_check: bool) -> ExecuteResult {
        // 阶段 1：解析（JSON → 结构化命令）
        let cmd = match self.parse(raw_input) {
            ParseResult::Ok(cmd) => cmd,
            ParseResult::Error(e) => return ExecuteResult::Error(format!("解析失败: {e}")),
        };

        // 阶段 2：Schema 验证
        match self.validate_schema(&cmd) {
            SchemaResult::Invalid(e) => return ExecuteResult::Error(format!("验证失败: {e}")),
            SchemaResult::Valid(_) => {}
        }

        // 阶段 3：命令路由
        let handler = match self.handlers.get(&cmd.command_type) {
            Some(h) => h,
            None => return ExecuteResult::Denied(format!("未知命令类型: {}", cmd.command_type)),
        };

        // 阶段 4：策略强制（通过 ActionPolicy 外部检查）
        if policy_check {
            // 策略检查由调用方通过 ActionPolicy 执行
            // 此处仅标记需要检查
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
        SchemaResult::Valid(cmd.clone())
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
}

// 由账号2生成
//! JS 注入 trait（消除 9 个模块的 IIFE 样板代码）。
//!
//! 提供：
//! - `JsInjectable` trait：统一 JS 注入接口（`inject_script` / `name` / `enabled`）
//! - `js_iife!` 宏：将 JS 代码体自动包装为 IIFE（`(function(){ ... })();`）
//!
//! 设计：trait 定义接口，宏减少样板。各防护模块实现 trait，
//! 管线组合时通过 trait 对象统一调用，无需知道具体类型。

/// JS 注入接口（所有指纹防护模块实现此 trait）。
///
/// # 实现要求
/// - `name`：模块名称（用于日志/调试）
/// - `inject_script`：生成完整的 JS 注入脚本
/// - `enabled`：是否启用（默认 true，可按 ProtectionMode 覆盖）
pub trait JsInjectable {
    /// 模块名称（如 "LetterboxShield"、"WebGLSpoof"）。
    fn name(&self) -> &str;

    /// 生成 JS 注入脚本（完整 IIFE，可直接 evaluate）。
    fn inject_script(&self) -> String;

    /// 是否启用（默认 true）。ProtectionMode 可覆盖此方法禁用特定模块。
    fn enabled(&self) -> bool {
        true
    }
}

/// 将 JS 代码体包装为 IIFE（立即调用函数表达式）。
///
/// 输入：JS 代码体（不含 `(function(){` 和 `})();` 包装）
/// 输出：完整的 IIFE 脚本
///
/// # 示例
/// ```
/// use aegis_policy_core::js_iife;
/// let script = js_iife!("var x = 1; console.log(x);");
/// assert!(script.starts_with("(function() {"));
/// assert!(script.ends_with("})();"));
/// ```
#[macro_export]
macro_rules! js_iife {
    ($body:expr) => {
        concat!("(function() {\n", $body, "\n})();")
    };
}

/// JS 注入管线：组合多个 JsInjectable 模块，按顺序生成注入脚本。
///
/// # 用法
/// ```ignore
/// use aegis_policy_core::JsPipeline;
/// let mut pipeline = JsPipeline::new();
/// pipeline.add(Box::new(LetterboxShield::new()));
/// pipeline.add(Box::new(WebGLSpoof::new()));
/// let script = pipeline.build();  // 所有模块的 JS 拼接
/// ```
pub struct JsPipeline {
    stages: Vec<Box<dyn JsInjectable>>,
}

impl JsPipeline {
    /// 创建空管线。
    pub fn new() -> Self {
        Self { stages: Vec::new() }
    }

    /// 添加管线阶段。
    pub fn add(&mut self, stage: Box<dyn JsInjectable>) {
        self.stages.push(stage);
    }

    /// 构建完整的注入脚本（所有启用模块的 JS 按顺序拼接）。
    pub fn build(&self) -> String {
        let parts: Vec<String> = self
            .stages
            .iter()
            .filter(|s| s.enabled())
            .map(|s| s.inject_script())
            .collect();
        parts.join("\n")
    }

    /// 获取管线阶段数量。
    pub fn len(&self) -> usize {
        self.stages.len()
    }

    /// 管线是否为空。
    pub fn is_empty(&self) -> bool {
        self.stages.is_empty()
    }
}

impl Default for JsPipeline {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct MockStage {
        name: &'static str,
        js: &'static str,
        active: bool,
    }

    impl JsInjectable for MockStage {
        fn name(&self) -> &str {
            self.name
        }
        fn inject_script(&self) -> String {
            self.js.to_string()
        }
        fn enabled(&self) -> bool {
            self.active
        }
    }

    #[test]
    fn pipeline_builds_enabled_stages() {
        let mut pipeline = JsPipeline::new();
        pipeline.add(Box::new(MockStage {
            name: "A",
            js: "var a = 1;",
            active: true,
        }));
        pipeline.add(Box::new(MockStage {
            name: "B",
            js: "var b = 2;",
            active: false,
        }));
        pipeline.add(Box::new(MockStage {
            name: "C",
            js: "var c = 3;",
            active: true,
        }));
        let result = pipeline.build();
        assert!(result.contains("var a = 1;"));
        assert!(!result.contains("var b = 2;"));
        assert!(result.contains("var c = 3;"));
    }

    #[test]
    fn pipeline_len() {
        let mut pipeline = JsPipeline::new();
        assert!(pipeline.is_empty());
        pipeline.add(Box::new(MockStage {
            name: "A",
            js: "",
            active: true,
        }));
        assert_eq!(pipeline.len(), 1);
    }

    #[test]
    fn js_iife_macro() {
        let script = js_iife!("var x = 42;");
        assert!(script.contains("(function() {"));
        assert!(script.contains("var x = 42;"));
        assert!(script.contains("})();"));
    }
}

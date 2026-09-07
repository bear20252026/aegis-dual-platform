//! Capability（照搬 cavi-ai/bobby-browser capability-scoped 控制面）。
//!
//! 所有适配器共享同一 capability/idempotency/evidence/checkpoint/event 契约，
//! Authentication fails closed，credentials never accepted in URLs or query strings。
//!
//! 职责：
//! - capability 定义（scope + 权限 + 约束）
//! - capability 验证（fail-closed——未知 capability 拒绝）
//! - capability 绑定（session/tab/generation——上下文隔离）
//!
//! 可拆卸：本模块不依赖 UI/网络/文件。
//! 可拼接：通过 Decision trait 与 broker/executor 层对接。

use std::collections::HashMap;

/// capability scope（照搬 bobby-browser capability 模型）。
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum CapabilityScope {
    /// 读取（navigation:read / tabs:read）。
    Read,
    /// 写入（download / export）——需确认。
    Write,
    /// 执行（navigate / update / 权限操作）——需授权。
    Execute,
    /// 管理（策略修改 / 系统配置）——高风险。
    Admin,
}

impl CapabilityScope {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "navigation:read" | "tabs:read" | "history:read" => Some(Self::Read),
            "download" | "export" | "file:write" => Some(Self::Write),
            "navigate" | "update" | "permission:grant" => Some(Self::Execute),
            "policy:modify" | "system:config" => Some(Self::Admin),
            _ => None,
        }
    }

    pub fn risk_level(&self) -> u8 {
        match self {
            Self::Read => 0,
            Self::Write => 1,
            Self::Execute => 2,
            Self::Admin => 3,
        }
    }
}

/// capability 定义（scope + 权限 + 约束）。
#[derive(Debug, Clone)]
pub struct Capability {
    pub name: String,
    pub scope: CapabilityScope,
    pub allowed_origins: Vec<String>,
    pub max_uses: Option<u32>,
    pub uses_count: u32,
}

impl Capability {
    pub fn is_exhausted(&self) -> bool {
        self.max_uses.is_some_and(|max| self.uses_count >= max)
    }

    pub fn is_origin_allowed(&self, origin: &str) -> bool {
        // 白名单按 origin 前缀精确匹配（此前 contains 子串匹配：白名单
        // "https://trusted.com" 放行 "https://evil-trusted.com/path"）。
        // 空白名单不再默认放行——显式 "*" 才表示全放行（fail-closed）。
        !self.allowed_origins.is_empty()
            && self.allowed_origins.iter().any(|o| {
                if o == "*" {
                    return true;
                }
                if origin.eq_ignore_ascii_case(o) {
                    return true;
                }
                // 入参可为同源完整 URL：origin 白名单值 + 路径/查询/锚点起始
                origin.len() > o.len()
                    && origin.starts_with(o.as_str())
                    && matches!(origin.as_bytes()[o.len()], b'/' | b'?' | b'#')
            })
    }
}

/// capability 注册表（fail-closed——未知 capability 拒绝）。
#[derive(Debug)]
pub struct CapabilityRegistry {
    capabilities: HashMap<String, Capability>,
}

impl Default for CapabilityRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl CapabilityRegistry {
    pub fn new() -> Self {
        Self {
            capabilities: HashMap::new(),
        }
    }

    /// 注册 capability。
    pub fn register(&mut self, cap: Capability) {
        self.capabilities.insert(cap.name.clone(), cap);
    }

    /// 验证 capability（fail-closed——未知拒绝）。
    pub fn validate(&self, name: &str, origin: &str) -> CapabilityResult {
        match self.capabilities.get(name) {
            None => CapabilityResult::Denied(format!("未知 capability: {name}")),
            Some(cap) => {
                if cap.is_exhausted() {
                    return CapabilityResult::Denied(format!(
                        "capability {name} 已耗尽（{}/{}）",
                        cap.uses_count,
                        cap.max_uses.unwrap_or(0)
                    ));
                }
                if !cap.is_origin_allowed(origin) {
                    return CapabilityResult::Denied(format!(
                        "origin {origin} 不在 capability {name} 的允许列表中"
                    ));
                }
                CapabilityResult::Allowed(cap.clone())
            }
        }
    }

    /// 消费 capability（增加使用计数）。
    pub fn consume(&mut self, name: &str) -> bool {
        if let Some(cap) = self.capabilities.get_mut(name) {
            if cap.is_exhausted() {
                return false;
            }
            cap.uses_count += 1;
            true
        } else {
            false
        }
    }
}

/// capability 验证结果（fail-closed）。
#[derive(Debug)]
pub enum CapabilityResult {
    Allowed(Capability),
    Denied(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cap(name: &str, scope: CapabilityScope, max: Option<u32>) -> Capability {
        Capability {
            name: name.into(),
            scope,
            // 显式全放行（空白名单已改为 fail-closed 拒绝——见回归测试）
            allowed_origins: vec!["*".into()],
            max_uses: max,
            uses_count: 0,
        }
    }

    #[test]
    fn empty_origin_list_denies() {
        // 回归：空白名单此前默认放行（fail-open）——现在 fail-closed
        let cap = Capability {
            name: "read".into(),
            scope: CapabilityScope::Read,
            allowed_origins: vec![],
            max_uses: None,
            uses_count: 0,
        };
        assert!(!cap.is_origin_allowed("https://example.com"));
    }

    #[test]
    fn origin_prefix_not_substring() {
        // 回归：此前 contains 子串匹配放行 evil-trusted.com
        let cap = Capability {
            name: "read".into(),
            scope: CapabilityScope::Read,
            allowed_origins: vec!["https://trusted.com".into()],
            max_uses: None,
            uses_count: 0,
        };
        assert!(!cap.is_origin_allowed("https://evil-trusted.com/path"));
        assert!(!cap.is_origin_allowed("https://xnottrusted.com"));
        assert!(cap.is_origin_allowed("https://trusted.com/path"));
        assert!(cap.is_origin_allowed("https://trusted.com"));
    }

    #[test]
    fn unknown_capability_denied() {
        let registry = CapabilityRegistry::new();
        assert!(matches!(
            registry.validate("unknown", "https://example.com"),
            CapabilityResult::Denied(_)
        ));
    }

    #[test]
    fn known_capability_allowed() {
        let mut registry = CapabilityRegistry::new();
        registry.register(make_cap("read", CapabilityScope::Read, None));
        assert!(matches!(
            registry.validate("read", "https://example.com"),
            CapabilityResult::Allowed(_)
        ));
    }

    #[test]
    fn exhausted_capability_denied() {
        let mut registry = CapabilityRegistry::new();
        registry.register(make_cap("limited", CapabilityScope::Write, Some(1)));
        registry.consume("limited");
        assert!(matches!(
            registry.validate("limited", "https://example.com"),
            CapabilityResult::Denied(_)
        ));
    }

    #[test]
    fn origin_filter_works() {
        let mut registry = CapabilityRegistry::new();
        let mut cap = make_cap("restricted", CapabilityScope::Execute, None);
        cap.allowed_origins = vec!["https://trusted.com".into()];
        registry.register(cap);
        assert!(matches!(
            registry.validate("restricted", "https://trusted.com/path"),
            CapabilityResult::Allowed(_)
        ));
        assert!(matches!(
            registry.validate("restricted", "https://evil.com"),
            CapabilityResult::Denied(_)
        ));
    }
}

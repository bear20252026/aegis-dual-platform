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
    /// 从动作名解析 scope（未知动作返回 None——调用方 fail-closed 处理）。
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "navigation:read" | "tabs:read" | "history:read" => Some(Self::Read),
            "download" | "export" | "file:write" => Some(Self::Write),
            "navigate" | "update" | "permission:grant" => Some(Self::Execute),
            "policy:modify" | "system:config" => Some(Self::Admin),
            _ => None,
        }
    }

    /// 风险等级（0..3 单调递增）——宿主 UI 据此分级展示确认强度。
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
    /// RS-105（审计 2026-09-25）：私有——外部篡改 pub 计数即可无限续用
    /// （耗尽语义失效）；推进唯一入口为 [`CapabilityRegistry::consume`]。
    uses_count: u32,
}

impl Capability {
    /// 构造 capability（uses_count 归零——模块外唯一构造入口）。
    pub fn new(
        name: impl Into<String>,
        scope: CapabilityScope,
        allowed_origins: Vec<String>,
        max_uses: Option<u32>,
    ) -> Self {
        Self {
            name: name.into(),
            scope,
            allowed_origins,
            max_uses,
            uses_count: 0,
        }
    }

    /// 已使用次数（只读——推进走 consume）。
    pub fn uses_count(&self) -> u32 {
        self.uses_count
    }

    /// 是否已达使用上限（无上限的 capability 永不耗尽）。
    pub fn is_exhausted(&self) -> bool {
        self.max_uses.is_some_and(|max| self.uses_count >= max)
    }

    /// origin 是否在该 capability 的允许列表内（fail-closed：空白名单拒绝，
    /// 显式 "*" 才全放行——语义细节见实现内 RS-104 注记）。
    pub fn is_origin_allowed(&self, origin: &str) -> bool {
        // 白名单按 origin 前缀精确匹配（此前 contains 子串匹配：白名单
        // "https://trusted.com" 放行 "https://evil-trusted.com/path"）。
        // 空白名单不再默认放行——显式 "*" 才表示全放行（fail-closed）。
        !self.allowed_origins.is_empty()
            && self.allowed_origins.iter().any(|o| {
                if o == "*" {
                    return true;
                }
                // RS-104（审计 2026-09-25）：白名单条目尾斜杠归一——
                // "https://trusted.com/" 此前对裸 origin
                // "https://trusted.com" 静默失效（eq 不等 + starts_with
                // 要求更长），条目形同虚设
                let o = o.strip_suffix('/').unwrap_or(o);
                if origin.eq_ignore_ascii_case(o) {
                    return true;
                }
                // 入参可为同源完整 URL：origin 白名单值 + 路径/查询/锚点起始
                origin.len() > o.len()
                    && origin.starts_with(o)
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
    /// 创建空注册表（fail-closed——未注册的 capability 一律拒绝）。
    pub fn new() -> Self {
        Self {
            capabilities: HashMap::new(),
        }
    }

    /// 注册 capability。
    ///
    /// RS-106（审计 2026-09-25）：返回被覆盖的旧 capability（None = 新增
    /// 注册）——此前静默覆盖，同名重注册无任何审计痕迹；调用方可对
    /// 非预期覆盖告警。
    pub fn register(&mut self, cap: Capability) -> Option<Capability> {
        self.capabilities.insert(cap.name.clone(), cap)
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
                // RS-222（2026-09-26 审计）：成功路径无载荷——此前
                // Allowed(cap.clone()) 克隆整个 Capability（name/scope/
                // allowed_origins Vec 全拷）；三层管线（broker::evaluate）
                // 仅消费判别即丢弃，纯热路径白付分配
                CapabilityResult::Allowed
            }
        }
    }

    /// 消费 capability（使用计数 +1；已耗尽或未注册返回 false）。
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
///
/// RS-222（2026-09-26 审计）：`Allowed` 无载荷——此前携带整个 Capability
/// 克隆，三层管线仅消费判别即丢弃（纯热路径分配）。
#[derive(Debug)]
pub enum CapabilityResult {
    Allowed,
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
            CapabilityResult::Allowed
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
            CapabilityResult::Allowed
        ));
        assert!(matches!(
            registry.validate("restricted", "https://evil.com"),
            CapabilityResult::Denied(_)
        ));
    }

    // —— RS-103/104/105/106 回归（审计 2026-09-25） ——

    #[test]
    fn scope_parse_full_vocabulary() {
        // RS-103：parse 词表全覆盖 + 未知拒绝
        for word in [
            "navigation:read",
            "tabs:read",
            "history:read",
            "download",
            "export",
            "file:write",
            "navigate",
            "update",
            "permission:grant",
            "policy:modify",
            "system:config",
        ] {
            assert!(CapabilityScope::parse(word).is_some(), "{word} 应合法");
        }
        assert_eq!(
            CapabilityScope::parse("navigation:read"),
            Some(CapabilityScope::Read)
        );
        assert_eq!(
            CapabilityScope::parse("download"),
            Some(CapabilityScope::Write)
        );
        assert_eq!(
            CapabilityScope::parse("navigate"),
            Some(CapabilityScope::Execute)
        );
        assert_eq!(
            CapabilityScope::parse("policy:modify"),
            Some(CapabilityScope::Admin)
        );
        // 大小写敏感 + 未知拒绝
        assert_eq!(CapabilityScope::parse("Download"), None);
        assert_eq!(CapabilityScope::parse(""), None);
        assert_eq!(CapabilityScope::parse("navigation:write"), None);
    }

    #[test]
    fn risk_level_ordering_is_read_write_execute_admin() {
        // RS-103：风险等级数值排序契约
        assert_eq!(CapabilityScope::Read.risk_level(), 0);
        assert_eq!(CapabilityScope::Write.risk_level(), 1);
        assert_eq!(CapabilityScope::Execute.risk_level(), 2);
        assert_eq!(CapabilityScope::Admin.risk_level(), 3);
    }

    #[test]
    fn exhaustion_boundary_is_at_max() {
        // RS-103：耗尽边界——uses == max 耗尽，max-1 未耗尽
        let cap = Capability::new("cap", CapabilityScope::Write, vec!["*".into()], Some(2));
        assert!(!cap.is_exhausted());
        let mut registry = CapabilityRegistry::new();
        registry.register(Capability::new(
            "c2",
            CapabilityScope::Write,
            vec!["*".into()],
            Some(2),
        ));
        assert!(registry.consume("c2"));
        assert!(matches!(
            registry.validate("c2", "https://e.com"),
            CapabilityResult::Allowed
        ));
        assert!(registry.consume("c2"));
        assert!(matches!(
            registry.validate("c2", "https://e.com"),
            CapabilityResult::Denied(_)
        ));
        assert!(!registry.consume("c2"), "耗尽后 consume 拒绝");
        // max_uses = None 不耗尽
        registry.register(Capability::new(
            "inf",
            CapabilityScope::Read,
            vec!["*".into()],
            None,
        ));
        for _ in 0..10 {
            assert!(registry.consume("inf"));
        }
    }

    #[test]
    fn whitelist_trailing_slash_normalized() {
        // RS-104：白名单条目尾斜杠归一——"https://trusted.com/" 此前对
        // 裸 origin 静默失效（条目形同虚设）
        let cap = Capability {
            name: "cap".into(),
            scope: CapabilityScope::Read,
            allowed_origins: vec!["https://trusted.com/".into()],
            max_uses: None,
            uses_count: 0,
        };
        assert!(
            cap.is_origin_allowed("https://trusted.com"),
            "裸 origin 必须命中带尾斜杠白名单"
        );
        assert!(cap.is_origin_allowed("https://trusted.com/path"));
        assert!(!cap.is_origin_allowed("https://evil.com"));
    }

    #[test]
    fn register_returns_overwritten_capability() {
        // RS-106：重注册返回旧值（审计痕迹）——新增返回 None
        let mut registry = CapabilityRegistry::new();
        assert!(registry
            .register(make_cap("dup", CapabilityScope::Read, None))
            .is_none());
        let old = registry.register(make_cap("dup", CapabilityScope::Write, None));
        assert!(old.is_some(), "覆盖必须返回旧 capability");
        assert_eq!(old.unwrap().scope, CapabilityScope::Read);
    }

    // —— RS-269 回归（审计 2026-10-01）：is_origin_allowed 三类边界 ——

    #[test]
    fn is_origin_allowed_total_for_hostile_inputs() {
        // RS-271：fuzz_capability_origin 的固定向量锚点——任意 origin 输入
        // 纯判定不 panic；空白名单恒拒 / "*" 恒放行两不变式
        let hostile = [
            "",
            "*",
            "https://",
            "https://*",
            "https://a@b@c:p/x",
            "你好.example",
        ];
        let long = format!("https://{}.com/", "a".repeat(100_000));
        let hostile: Vec<&str> = hostile.iter().copied().chain([long.as_str()]).collect();
        for origin in hostile {
            let empty = Capability::new("c", CapabilityScope::Execute, vec![], None);
            assert!(!empty.is_origin_allowed(origin), "空白名单恒拒");
            let wild = Capability::new("c", CapabilityScope::Execute, vec!["*".into()], None);
            assert!(wild.is_origin_allowed(origin), "显式 * 恒放行");
        }
    }

    #[test]
    fn origin_allowed_userinfo_url_fail_closed() {
        // RS-269：userinfo/@ 边界——白名单按 origin 前缀匹配，携带 userinfo
        // 的完整 URL（https://token@trusted.com/...）不命中裸 origin 白名单
        // （前缀即不同）。fail-closed 方向：含凭据形态宁可拒绝（调用方应
        // 先剥 userinfo 再传入 canonical origin）
        let cap = Capability {
            name: "cap".into(),
            scope: CapabilityScope::Execute,
            allowed_origins: vec!["https://trusted.com".into()],
            max_uses: None,
            uses_count: 0,
        };
        assert!(
            !cap.is_origin_allowed("https://token@trusted.com/path"),
            "userinfo URL 不得命中裸 origin 白名单（fail-closed）"
        );
        assert!(
            !cap.is_origin_allowed("https://user:pass@trusted.com/"),
            "user:pass@ 形态同样不命中"
        );
        // 剥离 userinfo 后的 canonical origin 正常命中（既有口径）
        assert!(cap.is_origin_allowed("https://trusted.com/path"));
    }

    #[test]
    fn origin_allowed_port_variant_fail_closed() {
        // RS-269：:port 边界——白名单 "https://trusted.com" 对带端口形态
        // （https://trusted.com:8443）不命中（端口差异即不同 origin，
        // 边界字符集不含 ':'）。需要放行端口变体必须显式登记该端口条目
        let cap = Capability {
            name: "cap".into(),
            scope: CapabilityScope::Execute,
            allowed_origins: vec!["https://trusted.com".into()],
            max_uses: None,
            uses_count: 0,
        };
        assert!(
            !cap.is_origin_allowed("https://trusted.com:8443/path"),
            "端口变体不得命中无端口白名单（origin 语义含端口）"
        );
        // 显式登记端口条目后命中（含子路径）
        let cap_port = Capability {
            name: "cap".into(),
            scope: CapabilityScope::Execute,
            allowed_origins: vec!["https://trusted.com:8443".into()],
            max_uses: None,
            uses_count: 0,
        };
        assert!(cap_port.is_origin_allowed("https://trusted.com:8443/path"));
        assert!(cap_port.is_origin_allowed("https://trusted.com:8443"));
        // 裸 origin 不命中带端口条目（对称 fail-closed）
        assert!(!cap_port.is_origin_allowed("https://trusted.com"));
    }

    #[test]
    fn origin_allowed_path_boundary_chars_exact() {
        // RS-269：路径首字符边界——仅 '/' '?' '#' 开启「origin + 路径」形态；
        // 其它字符（字母/点/冒号）拼接一律不命中
        let cap = Capability {
            name: "cap".into(),
            scope: CapabilityScope::Read,
            allowed_origins: vec!["https://trusted.com".into()],
            max_uses: None,
            uses_count: 0,
        };
        for ok_suffix in ["/path", "?q=1", "#frag"] {
            assert!(
                cap.is_origin_allowed(&format!("https://trusted.com{ok_suffix}")),
                "边界 {ok_suffix} 必须命中"
            );
        }
        for bad in [
            "https://trusted.com.evil.net",
            "https://trusted.com:8443",
            "https://trusted company.com",
            "https://xtrusted.com",
        ] {
            assert!(!cap.is_origin_allowed(bad), "非边界拼接 {bad} 不得命中");
        }
    }
}

// 由账号2生成
//! SpaceRouting（参照 Zen Browser nsZenSpaceRoutingManager / Arc Air Traffic Control）。
//!
//! 根据 URL 规则自动将链接路由到指定工作区（Workspace/Space）。
//! 支持域名匹配、路径匹配、正则匹配三种规则类型。
//!
//! 原始版权声明：
//!   Zen Browser space routing by Zen Browser Community (MPL-2.0)
//!   https://github.com/zen-browser/desktop
//!
//!   Arc Browser Air Traffic Control by The Browser Company
//!   https://arc.net
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 TabManager 中作为独立路由阶段调用。

use std::fmt;

/// 路由规则匹配类型。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MatchType {
    /// 域名匹配（包含子域名）。
    Domain,
    /// 路径前缀匹配。
    PathPrefix,
    /// 精确 URL 匹配。
    Exact,
}

/// 路由规则。
#[derive(Debug, Clone)]
pub struct RoutingRule {
    /// 规则名称。
    pub name: String,
    /// 匹配类型。
    pub match_type: MatchType,
    /// 匹配模式（域名/路径/URL）。
    pub pattern: String,
    /// 目标工作区 ID。
    pub workspace_id: String,
    /// 是否启用。
    pub enabled: bool,
}

impl RoutingRule {
    /// 创建域名匹配规则。
    ///
    /// RS-120（审计 2026-09-25）：域名大小写不敏感——构造时小写归一
    /// （hostname 侧由 extract_host 归一；路径/精确匹配保持原文——
    /// URL 路径按 RFC 3986 大小写敏感）。
    pub fn domain(name: &str, domain: &str, workspace_id: &str) -> Self {
        Self {
            name: name.to_string(),
            match_type: MatchType::Domain,
            pattern: domain.to_ascii_lowercase(),
            workspace_id: workspace_id.to_string(),
            enabled: true,
        }
    }

    /// 创建路径前缀匹配规则。
    pub fn path_prefix(name: &str, prefix: &str, workspace_id: &str) -> Self {
        Self {
            name: name.to_string(),
            match_type: MatchType::PathPrefix,
            pattern: prefix.to_string(),
            workspace_id: workspace_id.to_string(),
            enabled: true,
        }
    }

    /// 创建精确 URL 匹配规则。
    pub fn exact(name: &str, url: &str, workspace_id: &str) -> Self {
        Self {
            name: name.to_string(),
            match_type: MatchType::Exact,
            pattern: url.to_string(),
            workspace_id: workspace_id.to_string(),
            enabled: true,
        }
    }

    /// 检查 URL 是否匹配此规则。
    pub fn matches(&self, url: &str) -> bool {
        if !self.enabled {
            return false;
        }
        match self.match_type {
            MatchType::Domain => {
                // RS-121（审计 2026-09-25）：strip_suffix 前缀 '.' 语义检查
                // 替代 ends_with(format!(".{}", pattern))——消除每次匹配的
                // 堆分配。pattern 已构造时归一，但字段为 pub（直接构造
                // 绕过构造器），此处防御性再归一。
                let pattern = self.pattern.to_ascii_lowercase();
                // RS-119：空 pattern 不得命中——extract_host 失败返回 ""，
                // 空域匹配会把无 host 的 URL（about:blank 等）路由到该规则
                if pattern.is_empty() {
                    return false;
                }
                let hostname = extract_hostname(url);
                match hostname.strip_suffix(&pattern) {
                    // prefix 空 = 精确等值；否则必须是「.」边界（子域名）
                    Some(prefix) => prefix.is_empty() || prefix.ends_with('.'),
                    None => false,
                }
            }
            MatchType::PathPrefix => url.starts_with(&self.pattern),
            MatchType::Exact => url == self.pattern,
        }
    }
}

/// 从 URL 提取主机名（委托 util::extract_host，去端口+小写）。
fn extract_hostname(url: &str) -> String {
    crate::util::extract_host(url).unwrap_or_default()
}

/// SpaceRouting — URL 到工作区路由引擎。
///
/// 管理路由规则，根据 URL 决定目标工作区。
pub struct SpaceRouting {
    rules: Vec<RoutingRule>,
    /// 默认工作区 ID（无匹配规则时使用）。
    default_workspace: String,
}

impl fmt::Debug for SpaceRouting {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "SpaceRouting({} rules, default={})",
            self.rules.len(),
            self.default_workspace
        )
    }
}

impl SpaceRouting {
    /// 创建新的路由引擎。
    pub fn new(default_workspace: &str) -> Self {
        Self {
            rules: Vec::new(),
            default_workspace: default_workspace.to_string(),
        }
    }

    /// 添加路由规则。
    pub fn add_rule(&mut self, rule: RoutingRule) {
        self.rules.push(rule);
    }

    /// 批量添加路由规则。
    pub fn add_rules(&mut self, rules: Vec<RoutingRule>) {
        self.rules.extend(rules);
    }

    /// 根据 URL 路由到目标工作区。
    ///
    /// 返回第一个匹配规则的工作区 ID，无匹配则返回默认工作区。
    pub fn route(&self, url: &str) -> String {
        for rule in &self.rules {
            if rule.matches(url) {
                return rule.workspace_id.clone();
            }
        }
        self.default_workspace.clone()
    }

    /// 获取所有规则（只读）。
    pub fn rules(&self) -> &[RoutingRule] {
        &self.rules
    }

    /// 生成 SpaceRouting JS 注入脚本。
    ///
    /// 设置 `__AEGIS_SPACE_ROUTING` 全局对象，
    /// 提供 `route(url)` 方法供前端使用。
    pub fn inject_script(&self) -> String {
        // serde_json 构造——此前 name/workspace_id 完全未转义（JS 注入面）
        let rules_json: String = self
            .rules
            .iter()
            .map(|r| {
                serde_json::json!({
                    "name": r.name,
                    "type": match r.match_type {
                        MatchType::Domain => "domain",
                        MatchType::PathPrefix => "path",
                        MatchType::Exact => "exact",
                    },
                    "pattern": r.pattern,
                    "workspace": r.workspace_id,
                    // RS-038（审计 2026-09-24）：enabled 字段此前未进 JS——
                    // Rust 侧 matches() 检查 enabled，注入 JS 不检查（口径漂移）
                    "enabled": r.enabled,
                })
                .to_string()
            })
            .collect::<Vec<String>>()
            .join(",");
        // RS-037（审计 2026-09-24）：default_workspace 经 serde 转义——
        // 此前裸 format! 直拼单引号字面量（含 ' 即注入）
        let default_ws_json = serde_json::json!(self.default_workspace).to_string();
        format!(
            r#"
// Aegis SpaceRouting — URL 到工作区路由（参照 Zen Browser / Arc）
// 原始设计：Zen Browser (MPL-2.0) / Arc Browser (The Browser Company)
(function() {{
  var RULES = [{rules_json}];
  var DEFAULT_WS = {default_ws_json};

  function getHostname(url) {{
    try {{
      var u = new URL(url);
      return u.hostname;
    }} catch(e) {{ return ''; }}
  }}

  function route(url) {{
    for (var i = 0; i < RULES.length; i++) {{
      var r = RULES[i];
      // RS-038：禁用规则必须跳过（与 Rust matches() 口径一致）
      if (!r.enabled) continue;
      var matched = false;
      if (r.type === 'domain') {{
        var h = getHostname(url);
        matched = (h === r.pattern) || h.endsWith('.' + r.pattern);
      }} else if (r.type === 'path') {{
        matched = url.startsWith(r.pattern);
      }} else if (r.type === 'exact') {{
        matched = (url === r.pattern);
      }}
      if (matched) return r.workspace;
    }}
    return DEFAULT_WS;
  }}

  Object.defineProperty(window, '__AEGIS_SPACE_ROUTING', {{
    value: {{ route: route, rules: RULES, defaultWorkspace: DEFAULT_WS }},
    writable: false,
    configurable: false
  }});
}})();
"#
        )
    }
}

impl Default for SpaceRouting {
    fn default() -> Self {
        Self::new("default")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn domain_match_basic() {
        let rule = RoutingRule::domain("GitHub", "github.com", "work");
        assert!(rule.matches("https://github.com/user/repo"));
        assert!(rule.matches("https://api.github.com/repos"));
        assert!(!rule.matches("https://gitlab.com/user"));
    }

    #[test]
    fn domain_match_subdomain() {
        let rule = RoutingRule::domain("Google", "google.com", "search");
        assert!(rule.matches("https://www.google.com/search"));
        assert!(rule.matches("https://mail.google.com/inbox"));
        assert!(!rule.matches("https://example.com"));
    }

    #[test]
    fn path_prefix_match() {
        let rule = RoutingRule::path_prefix("Docs", "https://docs.example.com", "docs");
        assert!(rule.matches("https://docs.example.com/api"));
        assert!(!rule.matches("https://example.com/docs"));
    }

    #[test]
    fn exact_match() {
        let rule = RoutingRule::exact("Report", "https://example.com/report", "work");
        assert!(rule.matches("https://example.com/report"));
        assert!(!rule.matches("https://example.com/report/2"));
    }

    #[test]
    fn routing_engine_first_match_wins() {
        let mut sr = SpaceRouting::new("default");
        sr.add_rule(RoutingRule::domain("GitHub", "github.com", "work"));
        sr.add_rule(RoutingRule::domain("YouTube", "youtube.com", "media"));
        assert_eq!(sr.route("https://github.com/repo"), "work");
        assert_eq!(sr.route("https://youtube.com/watch"), "media");
        assert_eq!(sr.route("https://example.com"), "default");
    }

    #[test]
    fn disabled_rule_not_matched() {
        let mut rule = RoutingRule::domain("GitHub", "github.com", "work");
        rule.enabled = false;
        assert!(!rule.matches("https://github.com/repo"));
    }

    #[test]
    fn extract_hostname_various_urls() {
        assert_eq!(extract_hostname("https://github.com/repo"), "github.com");
        assert_eq!(extract_hostname("http://localhost:3000/path"), "localhost");
        assert_eq!(
            extract_hostname("https://sub.example.com:8080/"),
            "sub.example.com"
        );
    }

    #[test]
    fn script_contains_routing_logic() {
        let mut sr = SpaceRouting::new("default");
        sr.add_rule(RoutingRule::domain("GitHub", "github.com", "work"));
        let script = sr.inject_script();
        assert!(script.contains("__AEGIS_SPACE_ROUTING"));
        assert!(script.contains("github.com"));
        assert!(script.contains("route"));
    }

    // —— RS-037/038 回归（审计 2026-09-24） ——

    #[test]
    fn default_workspace_escaped_in_script() {
        // RS-037：default_workspace 含单引号此前直拼 `'{}'`——注入任意 JS
        let sr = SpaceRouting::new("ws'); alert(1); ('");
        let script = sr.inject_script();
        assert!(
            !script.contains("var DEFAULT_WS = 'ws');"),
            "default_workspace 必须经 serde 转义（不得逃逸字符串字面量）"
        );
        assert!(
            script.contains(r#""ws'); alert(1); ('""#),
            "serde JSON 字面量形态"
        );
    }

    #[test]
    fn script_carries_enabled_flag_and_short_circuits() {
        // RS-038：注入 JS 必须携带 enabled 字段并在 route 中跳过禁用规则
        let mut sr = SpaceRouting::new("default");
        let mut rule = RoutingRule::domain("GitHub", "github.com", "work");
        rule.enabled = false;
        sr.add_rule(rule);
        let script = sr.inject_script();
        assert!(
            script.contains(r#""enabled":false"#),
            "规则必须携带 enabled 字段"
        );
        assert!(
            script.contains("if (!r.enabled) continue;"),
            "route 必须短路禁用规则"
        );
    }

    #[test]
    fn script_escaping_malicious_rule_name_and_workspace() {
        // RS-047 回归（P28 修复面）：规则 name/workspace_id 源自用户配置，
        // 含双引号/反斜杠/换行/方括号/退出载荷——serde_json 构造保证其
        // 只作为 JSON 字符串字面量出现，不得逃逸出 RULES 数组产生 JS 注入
        let mut sr = SpaceRouting::new("default");
        let rule = RoutingRule::domain(
            r#"x"); alert(1); ([\"\n" injection"#,
            "github.com",
            r#"ws\"" + window.ev1l + \""#,
        );
        sr.add_rule(rule);
        let script = sr.inject_script();
        // name：输入 `x"); alert(1); ([\"\n" injection`——serde 逐字符转义
        // （\ → \\，" → \"）后作为 JSON 字符串内容出现
        assert!(
            script.contains(r#""name":"x\"); alert(1); ([\\\"\\n\" injection""#),
            "name 中的反斜杠/引号必须被 serde 转义为 JSON 字符串内容"
        );
        // name 载荷不得未转义逃逸出 JSON 字符串（裸 `");` 直连 RULES 即注入）
        assert!(
            !script.contains("RULES = [x\")"),
            "name 载荷不得逃逸 RULES 数组"
        );
        // workspace：输入 `ws\"" + window.ev1l + \"`——双引号与反斜杠均转义
        assert!(
            script.contains(r#""workspace":"ws\\\"\" + window.ev1l + \\\"""#),
            "workspace_id 中的双引号必须转义"
        );
        // 整体脚本可被 JSON 上下文解析（RULES 段不破坏语法）——直接验证
        // 提取 RULES 数组段为合法 JSON
        let start = script.find("var RULES = [").expect("RULES 段存在");
        let json_start = start + "var RULES = ".len();
        let json_end = script[json_start..].find("];").expect("RULES 数组闭合") + json_start;
        let rules_json = &script[json_start..=json_end];
        let parsed: serde_json::Value = serde_json::from_str(rules_json)
            .expect("RULES 段必须是合法 JSON（恶意 name 不破坏语法）");
        assert_eq!(parsed[0]["name"], r#"x"); alert(1); ([\"\n" injection"#);
        assert_eq!(parsed[0]["workspace"], r##"ws\"" + window.ev1l + \""##);
    }

    // —— RS-119/120/121（审计 2026-09-25）——

    #[test]
    fn domain_pattern_normalized_at_construction() {
        // RS-120：构造时小写归一——大写 pattern 必须命中小写 hostname
        let rule = RoutingRule::domain("Corp", "GitHub.COM", "work");
        assert!(rule.matches("https://github.com/repo"));
        assert!(rule.matches("https://API.GitHub.com/repos"));
        // 归一后存储（审计可观测）
        assert_eq!(rule.pattern, "github.com");
    }

    #[test]
    fn empty_domain_pattern_never_matches() {
        // RS-119：空 pattern 此前命中 extract_host 失败的 ""
        // （about:blank 等无 host URL 会被路由到该规则）——必须拒绝
        let mut rule = RoutingRule::domain("Empty", "", "work");
        assert!(!rule.matches("about:blank"));
        assert!(!rule.matches("https://github.com/repo"));
        assert!(!rule.matches("data:text/html,x"));
        // RS-038 语义保持：禁用规则同样不命中
        rule.enabled = false;
        assert!(!rule.matches("https://anything.com"));
    }

    #[test]
    fn empty_pattern_rule_falls_back_to_default_workspace() {
        // RS-119：路由引擎层面——空 pattern 规则不得吞掉无 host URL
        let mut sr = SpaceRouting::new("fallback");
        sr.add_rule(RoutingRule::domain("Empty", "", "trapped"));
        assert_eq!(sr.route("about:blank"), "fallback");
        assert_eq!(sr.route("https://github.com"), "fallback");
    }

    #[test]
    fn path_and_exact_prefixes_remain_case_sensitive() {
        // RS-119：路径/精确匹配保持原文大小写敏感（RFC 3986）——
        // 与域名归一语义形成对照（不得连带归一路径）
        let path_rule = RoutingRule::path_prefix("Docs", "https://docs.example.com/EN", "docs-en");
        assert!(path_rule.matches("https://docs.example.com/EN/api"));
        assert!(
            !path_rule.matches("https://docs.example.com/en/api"),
            "路径大小写敏感：小写 /en 不得命中 /EN 前缀"
        );
        let exact_rule = RoutingRule::exact("Report", "https://example.com/Report", "work");
        assert!(exact_rule.matches("https://example.com/Report"));
        assert!(!exact_rule.matches("https://example.com/report"));
    }

    #[test]
    fn suffix_match_requires_dot_boundary_no_allocation() {
        // RS-121 回归：strip_suffix + '.' 边界——"badcom" 不得命中 "com"，
        // "api.github.com" 命中 "github.com"，等值命中走 prefix.is_empty()
        let rule = RoutingRule::domain("Com", "com", "tld-ws");
        assert!(!rule.matches("https://badcom/"), "非 '.' 边界后缀不得命中");
        assert!(rule.matches("https://www.example.com/"));
        assert!(rule.matches("https://com/"));
    }
}

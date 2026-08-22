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
    pub fn domain(name: &str, domain: &str, workspace_id: &str) -> Self {
        Self {
            name: name.to_string(),
            match_type: MatchType::Domain,
            pattern: domain.to_string(),
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
                // 提取 URL 的域名部分
                let hostname = extract_hostname(url);
                hostname == self.pattern || hostname.ends_with(&format!(".{}", self.pattern))
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
        let rules_json: String = self
            .rules
            .iter()
            .map(|r| {
                format!(
                    r#"{{"name":"{}","type":"{}","pattern":"{}","workspace":"{}"}}"#,
                    r.name,
                    match r.match_type {
                        MatchType::Domain => "domain",
                        MatchType::PathPrefix => "path",
                        MatchType::Exact => "exact",
                    },
                    r.pattern.replace('"', "\\\""),
                    r.workspace_id
                )
            })
            .collect::<Vec<String>>()
            .join(",");
        let default_ws = &self.default_workspace;
        format!(
            r#"
// Aegis SpaceRouting — URL 到工作区路由（参照 Zen Browser / Arc）
// 原始设计：Zen Browser (MPL-2.0) / Arc Browser (The Browser Company)
(function() {{
  var RULES = [{rules_json}];
  var DEFAULT_WS = '{default_ws}';

  function getHostname(url) {{
    try {{
      var u = new URL(url);
      return u.hostname;
    }} catch(e) {{ return ''; }}
  }}

  function route(url) {{
    for (var i = 0; i < RULES.length; i++) {{
      var r = RULES[i];
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
}

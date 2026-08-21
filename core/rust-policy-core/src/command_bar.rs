// 由账号2生成
//! CommandBar（参照 Arc Browser Command Bar / Cmd+T）。
//!
//! 统一搜索标签/历史/书签/操作的命令面板，
//! 用户通过单一输入框快速找到任何内容或执行操作。
//!
//! 原始版权声明：
//!   Arc Browser Command Bar by The Browser Company
//!   https://arc.net
//!
//! 原始设计（Arc 文档）：
//!   "Arc's Command Bar (Cmd+T) is more than a URL bar. It provides
//!    universal search across tabs, history, bookmarks, and actions.
//!    Finding should be faster than organizing."
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在前端 UI 中作为独立组件调用。

use std::fmt;

/// 命令类型。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CommandType {
    /// 导航到 URL。
    Navigate,
    /// 切换到已打开的标签。
    SwitchTab,
    /// 搜索历史记录。
    SearchHistory,
    /// 搜索书签。
    SearchBookmark,
    /// 执行操作（新建标签/关闭标签/刷新等）。
    Action,
}

/// 命令条目。
#[derive(Debug, Clone)]
pub struct CommandEntry {
    /// 命令类型。
    pub command_type: CommandType,
    /// 显示标题。
    pub title: String,
    /// 副标题（URL/描述）。
    pub subtitle: String,
    /// 关联值（URL/action name/tab ID）。
    pub value: String,
    /// 图标标识。
    pub icon: String,
    /// 匹配关键词（用于搜索）。
    pub keywords: Vec<String>,
}

impl CommandEntry {
    /// 创建导航命令。
    pub fn navigate(title: &str, url: &str) -> Self {
        Self {
            command_type: CommandType::Navigate,
            title: title.to_string(),
            subtitle: url.to_string(),
            value: url.to_string(),
            icon: "globe".to_string(),
            keywords: vec![title.to_lowercase(), url.to_lowercase()],
        }
    }

    /// 创建切换标签命令。
    pub fn switch_tab(title: &str, tab_id: &str, url: &str) -> Self {
        Self {
            command_type: CommandType::SwitchTab,
            title: title.to_string(),
            subtitle: url.to_string(),
            value: tab_id.to_string(),
            icon: "tab".to_string(),
            keywords: vec![title.to_lowercase(), url.to_lowercase()],
        }
    }

    /// 创建搜索历史命令。
    pub fn search_history(title: &str, url: &str) -> Self {
        Self {
            command_type: CommandType::SearchHistory,
            title: title.to_string(),
            subtitle: url.to_string(),
            value: url.to_string(),
            icon: "clock".to_string(),
            keywords: vec![title.to_lowercase(), url.to_lowercase()],
        }
    }

    /// 创建书签命令。
    pub fn bookmark(title: &str, url: &str) -> Self {
        Self {
            command_type: CommandType::SearchBookmark,
            title: title.to_string(),
            subtitle: url.to_string(),
            value: url.to_string(),
            icon: "star".to_string(),
            keywords: vec![title.to_lowercase(), url.to_lowercase()],
        }
    }

    /// 创建操作命令。
    pub fn action(title: &str, description: &str, action_name: &str) -> Self {
        Self {
            command_type: CommandType::Action,
            title: title.to_string(),
            subtitle: description.to_string(),
            value: action_name.to_string(),
            icon: "command".to_string(),
            keywords: vec![title.to_lowercase(), description.to_lowercase()],
        }
    }

    /// 检查是否匹配查询。
    pub fn matches(&self, query: &str) -> bool {
        let q = query.to_lowercase();
        if q.is_empty() {
            return true;
        }
        self.keywords.iter().any(|k| k.contains(&q))
            || self.title.to_lowercase().contains(&q)
            || self.subtitle.to_lowercase().contains(&q)
            || self.value.to_lowercase().contains(&q)
    }
}

/// CommandBar — 统一命令搜索面板。
///
/// 管理命令条目，提供模糊搜索和执行。
pub struct CommandBar {
    entries: Vec<CommandEntry>,
    /// 最大返回结果数。
    max_results: usize,
}

impl fmt::Debug for CommandBar {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "CommandBar({} entries)", self.entries.len())
    }
}

impl CommandBar {
    /// 创建新的命令面板。
    pub fn new() -> Self {
        Self {
            entries: Vec::new(),
            max_results: 10,
        }
    }

    /// 设置最大返回结果数。
    pub fn with_max_results(mut self, max: usize) -> Self {
        self.max_results = max;
        self
    }

    /// 添加命令条目。
    pub fn add_entry(&mut self, entry: CommandEntry) {
        self.entries.push(entry);
    }

    /// 批量添加命令条目。
    pub fn add_entries(&mut self, entries: Vec<CommandEntry>) {
        self.entries.extend(entries);
    }

    /// 搜索匹配的命令。
    pub fn search(&self, query: &str) -> Vec<&CommandEntry> {
        self.entries
            .iter()
            .filter(|e| e.matches(query))
            .take(self.max_results)
            .collect()
    }

    /// 添加内置操作命令（新建标签/关闭标签/刷新/设置等）。
    pub fn add_builtin_actions(&mut self) {
        self.add_entry(CommandEntry::action("新建标签", "打开新标签页", "new_tab"));
        self.add_entry(CommandEntry::action(
            "关闭标签",
            "关闭当前标签页",
            "close_tab",
        ));
        self.add_entry(CommandEntry::action("刷新", "刷新当前页面", "reload"));
        self.add_entry(CommandEntry::action("后退", "返回上一页", "go_back"));
        self.add_entry(CommandEntry::action("前进", "前往下一页", "go_forward"));
        self.add_entry(CommandEntry::action(
            "隐私模式",
            "切换隐私浏览模式",
            "toggle_private",
        ));
        self.add_entry(CommandEntry::action("设置", "打开设置页面", "settings"));
        self.add_entry(CommandEntry::action(
            "清除数据",
            "清除浏览数据",
            "clear_data",
        ));
    }

    /// 生成 CommandBar JS 注入脚本。
    ///
    /// 设置 `__AEGIS_COMMAND_BAR` 全局对象，
    /// 提供 `search(query)` 和 `execute(entry)` 方法。
    pub fn inject_script(&self) -> String {
        let entries_json: String = self
            .entries
            .iter()
            .map(|e| {
                format!(
                    r#"{{"type":"{}","title":"{}","subtitle":"{}","value":"{}","icon":"{}"}}"#,
                    match e.command_type {
                        CommandType::Navigate => "navigate",
                        CommandType::SwitchTab => "switch_tab",
                        CommandType::SearchHistory => "history",
                        CommandType::SearchBookmark => "bookmark",
                        CommandType::Action => "action",
                    },
                    e.title.replace('"', "\\\""),
                    e.subtitle.replace('"', "\\\""),
                    e.value.replace('"', "\\\""),
                    e.icon
                )
            })
            .collect::<Vec<String>>()
            .join(",");
        let max = self.max_results;
        format!(
            r#"
// Aegis CommandBar — 统一命令搜索面板（参照 Arc Browser Cmd+T）
// 原始设计：The Browser Company / Arc Browser
(function() {{
  var ENTRIES = [{entries_json}];
  var MAX_RESULTS = {max};

  function search(query) {{
    var q = (query || '').toLowerCase();
    if (!q) return ENTRIES.slice(0, MAX_RESULTS);
    return ENTRIES.filter(function(e) {{
      return e.title.toLowerCase().indexOf(q) >= 0 ||
             e.subtitle.toLowerCase().indexOf(q) >= 0;
    }}).slice(0, MAX_RESULTS);
  }}

  function execute(entry) {{
    if (entry.type === 'navigate') {{
      window.location.href = entry.value;
    }} else if (entry.type === 'switch_tab') {{
      // 通过 postMessage 通知 Android WebView 切换标签
      window.postMessage({{ type: 'aegis:switch_tab', tabId: entry.value }}, '*');
    }} else if (entry.type === 'action') {{
      window.postMessage({{ type: 'aegis:action', action: entry.value }}, '*');
    }}
  }}

  Object.defineProperty(window, '__AEGIS_COMMAND_BAR', {{
    value: {{ search: search, execute: execute, entries: ENTRIES }},
    writable: false,
    configurable: false
  }});
}})();
"#
        )
    }
}

impl Default for CommandBar {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_matches_title() {
        let mut cb = CommandBar::new();
        cb.add_entry(CommandEntry::navigate("GitHub", "https://github.com"));
        let results = cb.search("git");
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].title, "GitHub");
    }

    #[test]
    fn search_matches_url() {
        let mut cb = CommandBar::new();
        cb.add_entry(CommandEntry::navigate("GitHub", "https://github.com"));
        let results = cb.search("github.com");
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn search_empty_returns_all() {
        let mut cb = CommandBar::new();
        cb.add_entry(CommandEntry::navigate("A", "https://a.com"));
        cb.add_entry(CommandEntry::navigate("B", "https://b.com"));
        let results = cb.search("");
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn search_respects_max_results() {
        let mut cb = CommandBar::new().with_max_results(2);
        for i in 0..10 {
            cb.add_entry(CommandEntry::navigate(
                &format!("Site{i}"),
                &format!("https://{i}.com"),
            ));
        }
        let results = cb.search("");
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn builtin_actions_added() {
        let mut cb = CommandBar::new();
        cb.add_builtin_actions();
        let results = cb.search("新建");
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].value, "new_tab");
    }

    #[test]
    fn action_command_matches() {
        let entry = CommandEntry::action("刷新", "刷新当前页面", "reload");
        assert!(entry.matches("刷新"));
        assert!(entry.matches("reload"));
        assert!(!entry.matches("关闭"));
    }

    #[test]
    fn script_contains_command_bar() {
        let cb = CommandBar::new();
        let script = cb.inject_script();
        assert!(script.contains("__AEGIS_COMMAND_BAR"));
        assert!(script.contains("search"));
        assert!(script.contains("execute"));
    }
}

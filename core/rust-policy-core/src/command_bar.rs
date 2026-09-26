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
    /// RS-039（审计 2026-09-24）：小写缓存——matches 此前每查询对
    /// title/subtitle/value 各做一次 to_lowercase（O(条目×查询) 分配）。
    title_lc: String,
    subtitle_lc: String,
    value_lc: String,
}

impl CommandEntry {
    /// RS-193（审计 2026-09-25）：单字段字符数上限——标题/子标题/值源自
    /// 书签/历史（页面可控），无上限时单条目可注入超大字符串（列表页
    /// 渲染面 + 内存放大）。截断按字符计（UTF-8 安全，不产生半字符）。
    const MAX_FIELD_CHARS: usize = 512;

    /// 内部统一构造器（keywords 与小写缓存单源派生；RS-193：字段截断）。
    fn new_entry(
        command_type: CommandType,
        title: &str,
        subtitle: &str,
        value: &str,
        icon: &str,
    ) -> Self {
        let truncate = |s: &str| s.chars().take(Self::MAX_FIELD_CHARS).collect::<String>();
        let title = truncate(title);
        let subtitle = truncate(subtitle);
        let value = truncate(value);
        let title_lc = title.to_lowercase();
        let subtitle_lc = subtitle.to_lowercase();
        let value_lc = value.to_lowercase();
        Self {
            command_type,
            title,
            subtitle,
            value,
            icon: icon.to_string(),
            keywords: vec![title_lc.clone(), subtitle_lc.clone()],
            title_lc,
            subtitle_lc,
            value_lc,
        }
    }

    /// 创建导航命令。
    pub fn navigate(title: &str, url: &str) -> Self {
        Self::new_entry(CommandType::Navigate, title, url, url, "globe")
    }

    /// 创建切换标签命令。
    pub fn switch_tab(title: &str, tab_id: &str, url: &str) -> Self {
        Self::new_entry(CommandType::SwitchTab, title, url, tab_id, "tab")
    }

    /// 创建搜索历史命令。
    pub fn search_history(title: &str, url: &str) -> Self {
        Self::new_entry(CommandType::SearchHistory, title, url, url, "clock")
    }

    /// 创建书签命令。
    pub fn bookmark(title: &str, url: &str) -> Self {
        Self::new_entry(CommandType::SearchBookmark, title, url, url, "star")
    }

    /// 创建操作命令。
    pub fn action(title: &str, description: &str, action_name: &str) -> Self {
        Self::new_entry(
            CommandType::Action,
            title,
            description,
            action_name,
            "command",
        )
    }

    /// 检查是否匹配查询。
    pub fn matches(&self, query: &str) -> bool {
        if query.is_empty() {
            return true;
        }
        // RS-039：title/subtitle/value 小写已预计算——此处仅查询侧一次
        // to_lowercase
        let q = query.to_lowercase();
        self.keywords.iter().any(|k| k.contains(&q))
            || self.title_lc.contains(&q)
            || self.subtitle_lc.contains(&q)
            || self.value_lc.contains(&q)
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

    /// 搜索匹配的命令（最多返回 max_results 条）。
    ///
    /// RS-165（审计 2026-09-25）：显式短路循环替代 `filter().take()` 链——
    /// 语义上惰性 take 已短路，但显式 `break` 让「命中满额即停」的意图
    /// 可读可审计，且杜绝未来有人改为 `.filter().collect()` 全量收集
    /// 再截断的回归形态。
    pub fn search(&self, query: &str) -> Vec<&CommandEntry> {
        // RS-122（审计 2026-09-25）：max_results=0 是合法配置（不展示）——
        // 此前 push 后判 `== max_results` 对 0 永假，上限静默失效、
        // 空查询也吐全量条目。提前返回空集兑现上限语义。
        if self.max_results == 0 {
            return Vec::new();
        }
        let mut results = Vec::new();
        for entry in &self.entries {
            if entry.matches(query) {
                results.push(entry);
                if results.len() == self.max_results {
                    break;
                }
            }
        }
        results
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
        // serde_json 构造——此前 format! 只转义双引号：标题/子标题源自书签
        // 历史（页面可控），含反斜杠/换行/控制字符即产生 JS 注入
        let entries_json: String = self
            .entries
            .iter()
            .map(|e| {
                serde_json::json!({
                    "type": match e.command_type {
                        CommandType::Navigate => "navigate",
                        CommandType::SwitchTab => "switch_tab",
                        CommandType::SearchHistory => "history",
                        CommandType::SearchBookmark => "bookmark",
                        CommandType::Action => "action",
                    },
                    "title": e.title,
                    "subtitle": e.subtitle,
                    "value": e.value,
                    "icon": e.icon,
                })
                .to_string()
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
      // RS-123（审计 2026-09-25）：与 Rust CommandEntry::matches 口径对齐——
      // Rust 侧含 value 通道（keywords+title+subtitle+value），此前 JS 漏
      // value（URL/action name 搜索结果两端不一致）
      return e.title.toLowerCase().indexOf(q) >= 0 ||
             e.subtitle.toLowerCase().indexOf(q) >= 0 ||
             e.value.toLowerCase().indexOf(q) >= 0;
    }}).slice(0, MAX_RESULTS);
  }}

  function execute(entry) {{
    if (entry.type === 'navigate') {{
      // 仅允许 http/https 目标（value 可源自历史/书签——javascript: 等拒绝）
      if (!/^https?:\/\//i.test(entry.value)) return;
      window.location.href = entry.value;
    }} else if (entry.type === 'switch_tab') {{
      // 通过 postMessage 通知 Android WebView 切换标签
      window.postMessage({{ type: 'aegis:switch_tab', tabId: entry.value }}, window.location.origin);
    }} else if (entry.type === 'action') {{
      window.postMessage({{ type: 'aegis:action', action: entry.value }}, window.location.origin);
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

    #[test]
    fn script_escaping_malicious_title_and_value() {
        // RS-048 回归（P27 修复面）：标题/子标题源自书签历史（页面可控），
        // 含双引号/反斜杠/换行/控制字符——serde_json 构造保证只作为 JSON
        // 字符串内容出现，不得逃逸 ENTRIES 数组产生 JS 注入
        let mut cb = CommandBar::new();
        cb.add_entry(CommandEntry::navigate(
            r#"x"); alert(1); (\" <script>"#,
            "https://e.com/a?b=\"quoted\"&c=1",
        ));
        let script = cb.inject_script();
        // title：输入 `x"); alert(1); (\" <script>`——serde 转义（\ → \\，" → \"）
        assert!(
            script.contains(r#""title":"x\"); alert(1); (\\\" <script>""#),
            "title 中的引号/反斜杠必须被 serde 转义"
        );
        // value：URL 内嵌引号同样转义
        assert!(
            script.contains(r#""value":"https://e.com/a?b=\"quoted\"&c=1""#),
            "value 中的双引号必须转义"
        );
        // 载荷不得未转义逃逸 ENTRIES 数组
        assert!(
            !script.contains("ENTRIES = [x\")"),
            "title 载荷不得逃逸 ENTRIES 数组"
        );
        // 整体脚本中 ENTRIES 段必须可被 JSON 解析（恶意 title 不破坏语法）
        let start = script.find("var ENTRIES = [").expect("ENTRIES 段存在");
        let json_start = start + "var ENTRIES = ".len();
        let json_end = script[json_start..].find("];").expect("ENTRIES 数组闭合") + json_start;
        let parsed: serde_json::Value = serde_json::from_str(&script[json_start..=json_end])
            .expect("ENTRIES 段必须是合法 JSON");
        assert_eq!(parsed[0]["title"], r#"x"); alert(1); (\" <script>"#);
    }

    #[test]
    fn script_execute_rejects_non_http_schemes() {
        // RS-048 联动：value 源自历史/书签（页面可控）——javascript: 等
        // scheme 必须被 execute 的 http/https 前缀门禁拒绝
        let cb = CommandBar::new();
        let script = cb.inject_script();
        assert!(
            script.contains("/^https?:\\/\\//i.test(entry.value)"),
            "execute 必须保留 http/https scheme 门禁"
        );
    }

    // —— RS-122/123（审计 2026-09-25）——

    #[test]
    fn empty_entries_search_returns_empty() {
        // RS-122：空集搜索——空查询与非空查询均不得 panic / 返回幻影条目
        let cb = CommandBar::new();
        assert!(cb.search("").is_empty());
        assert!(cb.search("anything").is_empty());
    }

    #[test]
    fn zero_max_results_yields_empty_even_for_empty_query() {
        // RS-122：max_results=0 是合法配置（用户可设置为不展示）——
        // 空查询也必须返回空集，不得绕过上限
        let mut cb = CommandBar::new().with_max_results(0);
        cb.add_entry(CommandEntry::navigate("GitHub", "https://github.com"));
        assert!(cb.search("").is_empty());
        assert!(cb.search("git").is_empty());
    }

    #[test]
    fn unicode_case_folding_matches() {
        // RS-122：to_lowercase 全 Unicode 折叠——带音标/非 ASCII 标题
        // 与查询的大小写变体必须互相命中
        let mut cb = CommandBar::new();
        cb.add_entry(CommandEntry::navigate("Über Straße Café", "https://e.com"));
        assert!(cb.search("über").len() == 1, "查询小写 ü 必须命中");
        assert!(cb.search("ÜBER").len() == 1, "大写查询折叠后必须命中");
        assert!(cb.search("CAFÉ").len() == 1);
        // 土耳其语式 İ 折叠：İ 小写化 = "i" + U+0307（两码元）——
        // 同形查询折叠后一致命中；裸 "i" 与 "i̇" 非子串关系（口径锁定：
        // 仅 to_lowercase，不做 NFKC 归一）
        let mut cb2 = CommandBar::new();
        cb2.add_entry(CommandEntry::navigate("İstanbul Guide", "https://e.com"));
        assert!(cb2.search("İstanbul").len() == 1, "同形查询折叠后必须命中");
        assert!(
            cb2.search("istanbul").is_empty(),
            "裸 i 与 i+U+0307 非子串关系——口径仅 to_lowercase（锁定防止误判为 bug）"
        );
    }

    #[test]
    fn search_covers_value_channel() {
        // RS-123：Rust matches() 覆盖 value 通道——按 URL 尾段/action name
        // 搜索必须命中（与 JS 注入脚本口径一致，断言见下一测试）
        let mut cb = CommandBar::new();
        cb.add_entry(CommandEntry::action("刷新", "刷新当前页面", "reload"));
        assert!(
            cb.search("reload").len() == 1,
            "value（action name）通道必须参与匹配"
        );
        cb.add_entry(CommandEntry::navigate(
            "X",
            "https://deep.example.com/secret/page",
        ));
        assert!(
            cb.search("secret/page").len() == 1,
            "value（URL）通道必须参与匹配"
        );
    }

    #[test]
    fn script_search_aligns_with_rust_value_channel() {
        // RS-123 回归：JS search 必须检查 value 通道（此前漏掉——
        // 与 Rust matches() 口径漂移）
        let cb = CommandBar::new();
        let script = cb.inject_script();
        assert!(
            script.contains("e.value.toLowerCase().indexOf(q) >= 0"),
            "JS search 必须覆盖 value 通道（与 Rust 口径对齐）"
        );
    }

    // —— RS-165/193/194（审计 2026-09-25）——

    #[test]
    fn oversized_fields_truncated_in_constructor() {
        // RS-193：构造器字段截断——页面可控的超长标题/子标题/值被钳制
        // 到 MAX_FIELD_CHARS 字符（按字符计，多字节 UTF-8 不产生半字符）
        let long = "汉".repeat(2_000); // 2000 chars（6000 bytes）
        let entry = CommandEntry::navigate(&long, &format!("https://e.com/{long}"));
        assert_eq!(
            entry.title.chars().count(),
            CommandEntry::MAX_FIELD_CHARS,
            "标题按字符数截断"
        );
        assert_eq!(
            entry.value.chars().count(),
            CommandEntry::MAX_FIELD_CHARS,
            "value 按字符数截断"
        );
        // 截断不破坏 UTF-8（title 仍是合法字符串——chars 计数即证明）
        assert!(entry.title.ends_with('汉'));
        // keywords 派生缓存同步截断
        assert_eq!(entry.keywords[0], entry.title.to_lowercase());
    }

    #[test]
    fn builtin_actions_all_eight_present() {
        // RS-194：8 个内置操作此前只测了「新建」——全量断言每条目的
        // title/value/类型，防止增删内置操作时测试静默漏护
        let mut cb = CommandBar::new();
        cb.add_builtin_actions();
        let expected = [
            ("新建标签", "new_tab"),
            ("关闭标签", "close_tab"),
            ("刷新", "reload"),
            ("后退", "go_back"),
            ("前进", "go_forward"),
            ("隐私模式", "toggle_private"),
            ("设置", "settings"),
            ("清除数据", "clear_data"),
        ];
        for (title, value) in expected {
            let hits: Vec<_> = cb.search(title);
            assert_eq!(hits.len(), 1, "标题「{title}」必须恰好命中一条");
            assert_eq!(hits[0].title, title);
            assert_eq!(hits[0].value, value, "「{title}」的 action name");
            assert!(matches!(hits[0].command_type, CommandType::Action));
        }
        // 英文 action name 通道（value）同样可搜
        assert_eq!(cb.search("toggle_private").len(), 1);
        assert_eq!(cb.search("clear_data").len(), 1);
        // 总数锁定（防止内置操作数量漂移）
        assert_eq!(cb.search("").len(), 8);
    }
}

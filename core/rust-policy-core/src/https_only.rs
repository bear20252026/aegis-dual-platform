//! HttpsOnly 模式（照搬 voidbrowser privacy/https_only.rs 本地化适配）。
//!
//! 强制所有导航升级为 HTTPS，跟踪用户手动放行的域。
//! 所有状态仅在会话内有效，浏览器关闭即重置。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：通过 `Decision` trait 与 broker/executor 层对接。

use std::collections::{HashMap, HashSet};

/// RS-116：upgrade_counts 有界上限——恶意/异常页面无限换 tab_id 会让
/// HashMap 无界增长（内存耗尽面）。池满后新 tab 不再计数（仅遥测降级，
/// 升级判定不受影响）；total_upgrades 为 u64 标量饱和累加，无内存面。
const MAX_TRACKED_TABS: usize = 4096;

/// HTTPS-Only 模式状态。
#[derive(Debug)]
pub struct HttpsOnlyState {
    /// 用户手动放行的 HTTP 域名（会话内有效）。
    allowed_http_domains: HashSet<String>,
    /// 每个 tab 的 HTTPS 升级计数。
    upgrade_counts: HashMap<String, u64>,
    /// 全局 HTTPS 升级计数。
    total_upgrades: u64,
}

impl Default for HttpsOnlyState {
    fn default() -> Self {
        Self::new()
    }
}

impl HttpsOnlyState {
    pub fn new() -> Self {
        Self {
            allowed_http_domains: HashSet::new(),
            upgrade_counts: HashMap::new(),
            total_upgrades: 0,
        }
    }

    /// 检查域名是否被用户手动放行（允许 HTTP）。
    /// M-13 修复（审计 2026-08-31）：大小写不敏感比较。
    pub fn is_http_allowed(&self, domain: &str) -> bool {
        let lowered = domain.to_ascii_lowercase();
        self.allowed_http_domains.contains(&lowered)
    }

    /// 用户手动放行 HTTP 域名（M-13：统一小写归一存储）。
    pub fn allow_http(&mut self, domain: &str) {
        self.allowed_http_domains
            .insert(domain.to_ascii_lowercase());
    }

    /// 尝试将 HTTP URL 升级为 HTTPS。
    /// - 如果已是 HTTPS，返回 None（无需处理）。
    /// - 如果 HTTP 且域名已放行，返回 None（允许 HTTP）。
    /// - 否则返回升级后的 HTTPS URL。
    ///
    /// M-13 修复（审计 2026-08-31）：scheme 判断原为大小写敏感的
    /// `starts_with("http://")`——`HTTP://` 可绕过强制升级；域名比较
    /// 同步做 ASCII 小写归一。
    ///
    /// RS-118（审计 2026-09-25）：一次 7 字节前缀比较替代全串
    /// `to_ascii_lowercase` + 两次 `find("://")`（消除 O(全串) 分配与重复扫描）。
    /// RS-117（审计 2026-09-25）：authority 先剥 userinfo 再去端口——
    /// 此前 `http://user:pass@host` 把 "user" 当域名参与放行判定。
    pub fn upgrade(&mut self, url: &str, tab_id: &str) -> Option<String> {
        let rest = match url.get(..7) {
            Some(prefix) if prefix.eq_ignore_ascii_case("http://") => &url[7..],
            _ => return None, // 已是 HTTPS 或非 HTTP
        };

        // authority 终止符含 / ? #（query/fragment 不得混入 host）
        let authority_end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
        let authority = &rest[..authority_end];
        // RS-117：剥 userinfo（最后一个 @ 之前的部分属于凭据，不是 host）
        let after_userinfo = match authority.rsplit_once('@') {
            Some((_, h)) => h,
            None => authority,
        };
        // 端口差异不影响放行判定（归一比较）；IPv6 裸冒号 host 在此退化为
        // 无法命中白名单——fail-closed 方向（不放行 → 走强制升级）
        let domain = after_userinfo
            .split(':')
            .next()
            .unwrap_or("")
            .to_ascii_lowercase();
        if self.is_http_allowed(&domain) {
            return None; // 用户已放行
        }

        // 升级为 HTTPS（保留原 URL 其余部分——userinfo/端口/query 原样）
        let upgraded = format!("https://{rest}");
        // RS-116：计数有界——既有 tab 递增；新 tab 仅在池未满时入账
        if let Some(count) = self.upgrade_counts.get_mut(tab_id) {
            *count = count.saturating_add(1);
        } else if self.upgrade_counts.len() < MAX_TRACKED_TABS {
            self.upgrade_counts.insert(tab_id.to_string(), 1);
        }
        self.total_upgrades = self.total_upgrades.saturating_add(1);
        Some(upgraded)
    }

    /// 获取 tab 的升级计数。
    pub fn get_upgrade_count(&self, tab_id: &str) -> u64 {
        self.upgrade_counts.get(tab_id).copied().unwrap_or(0)
    }

    /// 获取全局升级计数。
    pub fn get_total_upgrades(&self) -> u64 {
        self.total_upgrades
    }

    /// 重置 tab 计数（新导航时）。
    pub fn reset_tab(&mut self, tab_id: &str) {
        self.upgrade_counts.remove(tab_id);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn http_url_upgraded() {
        let mut state = HttpsOnlyState::new();
        let result = state.upgrade("http://example.com/path", "tab-1");
        assert_eq!(result, Some("https://example.com/path".to_string()));
        assert_eq!(state.get_upgrade_count("tab-1"), 1);
    }

    #[test]
    fn https_url_unchanged() {
        let mut state = HttpsOnlyState::new();
        let result = state.upgrade("https://example.com", "tab-1");
        assert_eq!(result, None);
    }

    #[test]
    fn allowed_domain_not_upgraded() {
        let mut state = HttpsOnlyState::new();
        state.allow_http("http-only.example.com");
        let result = state.upgrade("http://http-only.example.com/page", "tab-1");
        assert_eq!(result, None);
    }

    #[test]
    fn total_upgrades_across_tabs() {
        let mut state = HttpsOnlyState::new();
        state.upgrade("http://a.com", "t1");
        state.upgrade("http://b.com", "t2");
        assert_eq!(state.get_total_upgrades(), 2);
    }
    #[test]
    fn uppercase_scheme_is_upgraded() {
        // M-13 回归：HTTP:// 大写 scheme 不得绕过强制升级
        let mut state = HttpsOnlyState::new();
        let result = state.upgrade("HTTP://example.com/path", "tab-1");
        assert_eq!(result, Some("https://example.com/path".to_string()));
    }

    #[test]
    fn allowed_domain_case_insensitive() {
        // M-13 回归：放行域名与请求域名大小写不同也必须命中
        let mut state = HttpsOnlyState::new();
        state.allow_http("HTTP-Only.Example.COM");
        assert_eq!(
            state.upgrade("http://http-only.example.com/page", "tab-1"),
            None
        );
        assert_eq!(
            state.upgrade("http://HTTP-ONLY.EXAMPLE.COM/page", "tab-1"),
            None
        );
    }

    // —— 边界补强：host 提取与计数语义（此前 6 例未覆盖）——

    #[test]
    fn port_preserved_in_upgrade_and_same_allowed_match() {
        // 带端口的 http URL 升级保留端口；放行判定忽略端口差异
        let mut state = HttpsOnlyState::new();
        assert_eq!(
            state.upgrade("http://example.com:8080/a", "t1"),
            Some("https://example.com:8080/a".to_string())
        );
        state.allow_http("example.com");
        // 放行后，带端口请求不再升级
        assert_eq!(state.upgrade("http://example.com:8080/a", "t1"), None);
    }

    #[test]
    fn query_and_fragment_not_treated_as_host() {
        // http://x.com?a=1 的域名必须是 x.com，query 不得混入 host
        let mut state = HttpsOnlyState::new();
        let upgraded = state.upgrade("http://example.com?a=1", "t1");
        assert_eq!(upgraded, Some("https://example.com?a=1".to_string()));
        let frag = state.upgrade("http://example.com#sec", "t2");
        assert_eq!(frag, Some("https://example.com#sec".to_string()));
    }

    #[test]
    fn upgrade_counts_are_per_tab_and_resetable() {
        let mut state = HttpsOnlyState::new();
        state.upgrade("http://a.com", "t1");
        state.upgrade("http://a.com/2", "t1");
        state.upgrade("http://b.com", "t2");
        assert_eq!(state.get_upgrade_count("t1"), 2);
        assert_eq!(state.get_upgrade_count("t2"), 1);
        assert_eq!(state.get_upgrade_count("t-unknown"), 0);
        state.reset_tab("t1");
        assert_eq!(state.get_upgrade_count("t1"), 0);
        // 全局计数保留
        assert_eq!(state.get_total_upgrades(), 3);
    }

    #[test]
    fn non_http_scheme_ignored() {
        // 非 http 协议（ftp/blob 等）不走升级，也不计入放行判定
        let mut state = HttpsOnlyState::new();
        assert_eq!(state.upgrade("ftp://example.com/f", "t1"), None);
        assert_eq!(state.upgrade("https://example.com", "t2"), None);
        assert_eq!(state.get_total_upgrades(), 0);
    }

    // —— RS-116/117/118（审计 2026-09-25）——

    #[test]
    fn userinfo_is_stripped_before_allowlist_lookup() {
        // RS-117：http://user:pass@host 此前把 "user" 当域名——
        // userinfo 必须剥离后再参与放行判定；升级 URL 保留原 userinfo
        let mut state = HttpsOnlyState::new();
        assert_eq!(
            state.upgrade("http://user:pass@example.com/path", "t1"),
            Some("https://user:pass@example.com/path".to_string())
        );
        state.allow_http("example.com");
        assert_eq!(
            state.upgrade("http://user:pass@example.com/path", "t1"),
            None,
            "userinfo 剥离后必须命中放行（不得把凭据当域名）"
        );
        assert_eq!(state.get_upgrade_count("t1"), 1);
    }

    #[test]
    fn trailing_dot_domain_fails_closed_to_upgrade() {
        // RS-117：DNS 尾点形式（example.com.）与放行域不同——
        // fail-closed：不放行，走强制升级（安全方向）
        let mut state = HttpsOnlyState::new();
        state.allow_http("example.com");
        assert_eq!(
            state.upgrade("http://example.com./path", "t1"),
            Some("https://example.com./path".to_string())
        );
    }

    #[test]
    fn upgrade_counts_bounded_new_tabs_untracked_when_full() {
        // RS-116：池满后新 tab 不入账（遥测降级），升级判定不受影响；
        // total_upgrades 继续饱和累加
        let mut state = HttpsOnlyState::new();
        for i in 0..MAX_TRACKED_TABS {
            state.upgrade("http://a.com", &format!("tab-{i}"));
        }
        assert_eq!(state.get_total_upgrades() as usize, MAX_TRACKED_TABS);
        // 池满后的新 tab：升级仍执行，但不再计数
        assert_eq!(
            state.upgrade("http://b.com", "tab-overflow"),
            Some("https://b.com".to_string())
        );
        assert_eq!(state.get_upgrade_count("tab-overflow"), 0);
        assert_eq!(
            state.get_total_upgrades() as usize,
            MAX_TRACKED_TABS + 1,
            "全局 u64 计数不受池上限约束"
        );
        // 既有 tab 仍正常计数
        assert_eq!(state.get_upgrade_count("tab-0"), 1);
    }

    #[test]
    fn upgrade_counts_saturate_never_overflow() {
        // RS-116：saturating_add——u64 溢出不可能（防御性锁定）
        let mut state = HttpsOnlyState::new();
        let tab = "t1";
        // 直接触碰内部计数（白盒：模拟天文数字升级次数）
        state.upgrade_counts.insert(tab.to_string(), u64::MAX);
        state.upgrade("http://a.com", tab);
        assert_eq!(state.get_upgrade_count(tab), u64::MAX);
    }
}

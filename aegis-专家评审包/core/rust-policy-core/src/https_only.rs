//! HttpsOnly 模式（照搬 voidbrowser privacy/https_only.rs 本地化适配）。
//!
//! 强制所有导航升级为 HTTPS，跟踪用户手动放行的域。
//! 所有状态仅在会话内有效，浏览器关闭即重置。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：通过 `Decision` trait 与 broker/executor 层对接。

use std::collections::{HashMap, HashSet};

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
    pub fn is_http_allowed(&self, domain: &str) -> bool {
        self.allowed_http_domains.contains(domain)
    }

    /// 用户手动放行 HTTP 域名。
    pub fn allow_http(&mut self, domain: &str) {
        self.allowed_http_domains.insert(domain.to_string());
    }

    /// 尝试将 HTTP URL 升级为 HTTPS。
    /// - 如果已是 HTTPS，返回 None（无需处理）。
    /// - 如果 HTTP 且域名已放行，返回 None（允许 HTTP）。
    /// - 否则返回升级后的 HTTPS URL。
    pub fn upgrade(&mut self, url: &str, tab_id: &str) -> Option<String> {
        if !url.starts_with("http://") {
            return None; // 已是 HTTPS 或非 HTTP
        }

        // 提取域名
        let domain = url.split("://").nth(1)?.split('/').next()?;
        if self.is_http_allowed(domain) {
            return None; // 用户已放行
        }

        // 升级为 HTTPS
        let upgraded = url.replacen("http://", "https://", 1);
        let count = self.upgrade_counts.entry(tab_id.to_string()).or_insert(0);
        *count += 1;
        self.total_upgrades += 1;
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
}

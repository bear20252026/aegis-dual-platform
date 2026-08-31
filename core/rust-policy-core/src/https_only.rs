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
    pub fn upgrade(&mut self, url: &str, tab_id: &str) -> Option<String> {
        let lowered = url.to_ascii_lowercase();
        if !lowered.starts_with("http://") {
            return None; // 已是 HTTPS 或非 HTTP
        }

        // 提取域名（scheme 后到第一个 / 或 :port 之前——含端口也一并
        // 归一比较，端口差异不影响放行判定）
        let rest = &url[url.find("://").map(|i| i + 3).unwrap_or(0)..];
        let host_end = rest.find(['/', ':']).unwrap_or(rest.len());
        let domain = rest[..host_end].to_ascii_lowercase();
        if self.is_http_allowed(&domain) {
            return None; // 用户已放行
        }

        // 升级为 HTTPS
        let upgraded = format!(
            "https://{}",
            &url[url.find("://").map(|i| i + 3).unwrap_or(0)..]
        );
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
}

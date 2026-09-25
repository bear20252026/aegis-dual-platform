/*
 * adblock.rs — 广告/追踪拦截器（照搬 Omni Browser AdBlockManager.kt 本地化适配）。
 *
 * 原始版权：Omni Browser - Copyright (C) 2026 RebelRoot Ltd
 * 原始许可：GNU General Public License v3.0
 * 来源：https://github.com/REBEL-ROOT/omni-browser
 * 改动：将 Kotlin 实现翻译为 Rust，适配 Aegis 架构（无 Android 依赖）。
 */

use std::collections::HashSet;

/// 广告拦截提供者（照搬 Omni Browser AdBlockProvider）。
#[derive(Debug, Clone)]
pub struct AdBlockProvider {
    pub id: String,
    pub name: String,
    pub url: String,
    pub is_preset: bool,
    pub is_enabled: bool,
    pub rule_count: usize,
    pub last_updated: u64,
}

/// 广告/追踪拦截管理器（照搬 Omni Browser AdBlockManager）。
#[derive(Debug)]
pub struct AdBlockManager {
    providers: Vec<AdBlockProvider>,
    blocked_domains: HashSet<String>,
    total_blocked: u64,
    is_enabled: bool,
}

impl Default for AdBlockManager {
    fn default() -> Self {
        Self::new()
    }
}

impl AdBlockManager {
    /// 预设拦截列表（照搬 Omni Browser PRESET_PROVIDERS）。
    pub fn preset_providers() -> Vec<AdBlockProvider> {
        vec![
            AdBlockProvider {
                id: "easylist_base".into(),
                name: "EasyList Base (Ads & Banners)".into(),
                url: "https://easylist.to/easylist/easylist.txt".into(),
                is_preset: true,
                is_enabled: true,
                rule_count: 0,
                last_updated: 0,
            },
            AdBlockProvider {
                id: "adguard_base".into(),
                name: "AdGuard Base Filter".into(),
                url: "https://filters.adtidy.org/extension/ublock/filters/2.txt".into(),
                is_preset: true,
                is_enabled: true,
                rule_count: 0,
                last_updated: 0,
            },
            AdBlockProvider {
                id: "adguard_anti_adblock".into(),
                name: "AdGuard Anti-AdBlock Defusers".into(),
                url: "https://filters.adtidy.org/extension/ublock/filters/14.txt".into(),
                is_preset: true,
                is_enabled: true,
                rule_count: 0,
                last_updated: 0,
            },
            AdBlockProvider {
                id: "peter_lowe".into(),
                name: "Peter Lowe's Ad & Tracker List".into(),
                url: "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=hosts&showintro=0&mimetype=plaintext".into(),
                is_preset: true,
                is_enabled: true,
                rule_count: 0,
                last_updated: 0,
            },
            AdBlockProvider {
                id: "fanboy_social".into(),
                name: "Fanboy Social Tracking Blocker".into(),
                url: "https://easylist.to/easylist/fanboy-social.txt".into(),
                is_preset: true,
                is_enabled: true,
                rule_count: 0,
                last_updated: 0,
            },
        ]
    }

    /// 创建管理器：装载预设拦截列表提供者，黑名单为空、计数清零、
    /// 默认启用（RS-067：补文档）。
    pub fn new() -> Self {
        Self {
            providers: Self::preset_providers(),
            blocked_domains: HashSet::new(),
            total_blocked: 0,
            is_enabled: true,
        }
    }

    /// 加载域名黑名单（从 filter list 解析的 host 格式）。
    pub fn load_blocked_domains(&mut self, domains: impl IntoIterator<Item = String>) {
        self.blocked_domains.extend(domains);
    }

    /// 检查 URL 是否应被拦截。
    ///
    /// RS-066（审计 2026-09-25）：父域链迭代包含 TLD 本身（example.com
    /// → com）——黑名单登记 TLD（如 "com"）即拦截该 TLD 下全部站点。
    /// 这是有意保留的语义（hosts 形 filter list 允许登记 TLD 做整域
    /// 拦截），不是缺陷；调用方若需防误配，应在加载黑名单时校验条目。
    ///
    /// RS-069：本方法每次调用经 extract_host 分配归一化 String。
    /// 高频调用方 / 已持有归一化 host 的调用方应改用
    /// [`AdBlockManager::should_block_host`]（预归一 API，零分配）。
    pub fn should_block(&mut self, url: &str) -> bool {
        match Self::extract_host(url) {
            Some(host) => self.should_block_host(&host),
            None => false,
        }
    }

    /// 检查已归一化（小写、无端口、无 userinfo）的主机名是否应被拦截。
    ///
    /// RS-069（审计 2026-09-25）预归一 API：调用方绕过 URL 解析与
    /// to_lowercase 分配；语义与 [`AdBlockManager::should_block`]
    /// 完全一致（含父域链迭代与命中计数）。
    pub fn should_block_host(&mut self, host: &str) -> bool {
        if !self.is_enabled {
            return false;
        }
        if self.blocked_domains.contains(host) {
            self.total_blocked += 1;
            return true;
        }
        // H-8 修复（审计 2026-08-31）：父域链迭代匹配——原实现是
        // host.split('.') 逐「单段」精确比对（ads.example.com 会拿
        // ads/example/com 三个单词查表），黑名单含常见单词域即大面积
        // 误拦、两段父域（ads.com）永远无法命中。改为逐级剥去最左
        // 标签：a.ads.com → ads.com → com（真正的父域链检查）。
        let mut h = host;
        while let Some((_, rest)) = h.split_once('.') {
            h = rest;
            if self.blocked_domains.contains(h) {
                self.total_blocked += 1;
                return true;
            }
        }
        false
    }

    /// 从 URL 提取主机名（委托 util::extract_host）。
    fn extract_host(url: &str) -> Option<String> {
        crate::util::extract_host(url)
    }

    /// 获取拦截计数。
    pub fn total_blocked(&self) -> u64 {
        self.total_blocked
    }

    /// 重置拦截计数。
    pub fn reset_stats(&mut self) {
        self.total_blocked = 0;
    }

    /// 启用/禁用拦截。
    pub fn set_enabled(&mut self, enabled: bool) {
        self.is_enabled = enabled;
    }

    /// 获取提供者列表。
    pub fn providers(&self) -> &[AdBlockProvider] {
        &self.providers
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blocked_domain_detected() {
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        assert!(mgr.should_block("https://ads.example.com/banner"));
        assert_eq!(mgr.total_blocked(), 1);
    }

    #[test]
    fn non_blocked_domain_allowed() {
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        assert!(!mgr.should_block("https://safe.example.com/"));
    }

    #[test]
    fn disabled_manager_allows_all() {
        let mut mgr = AdBlockManager::new();
        mgr.set_enabled(false);
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        assert!(!mgr.should_block("https://ads.example.com/banner"));
    }

    #[test]
    fn preset_providers_exist() {
        let mgr = AdBlockManager::new();
        assert!(mgr.providers().len() >= 4);
    }
    #[test]
    fn parent_domain_iteration_blocks_registered_parent() {
        // H-8 回归：黑名单 ads.com 必须命中 a.ads.com（旧实现逐单段
        // 匹配——两段父域永远无法命中）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.com".into()]);
        assert!(mgr.should_block("https://a.ads.com/x"));
        assert!(mgr.should_block("https://b.c.ads.com/x"));
    }

    #[test]
    fn parent_domain_no_false_positive_on_single_label() {
        // H-8 回归：黑名单含常见单词段时不得误拦无关站点
        // （旧实现会把 host 拆成单段逐词查表——"app"、"m" 等单词段
        // 误命中；com.app.com 不得因 "com" 入黑名单而全网误拦）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["tracker.app".into()]);
        assert!(!mgr.should_block("https://my.app.example.com/x"));
        assert!(mgr.should_block("https://tracker.app/x"));
    }

    // —— RS-065/069 回归（审计 2026-09-25） ——

    #[test]
    fn block_rules_survive_port_case_and_bare_host() {
        // RS-065：URL 形态变体——端口剥离/大小写归一/裸 host 全部命中
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        assert!(
            mgr.should_block("https://ads.example.com:8080/banner"),
            "带端口命中"
        );
        assert!(
            mgr.should_block("HTTPS://ADS.EXAMPLE.COM/x"),
            "大写 URL 归一命中"
        );
        assert!(mgr.should_block("ads.example.com"), "裸 host 命中");
    }

    #[test]
    fn malformed_urls_never_panic_and_never_block() {
        // RS-065：畸形 URL fail-closed——不拦截、不 panic
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        assert!(!mgr.should_block(""));
        assert!(!mgr.should_block("https://"));
        assert!(!mgr.should_block("2001:db8::1"));
        assert!(!mgr.should_block("https://[unclosed/x"));
    }

    #[test]
    fn should_block_host_matches_url_semantics() {
        // RS-069：预归一 API 与 should_block 语义一致（含父域命中计数）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.com".into()]);
        assert!(mgr.should_block_host("a.ads.com"));
        assert_eq!(mgr.total_blocked(), 1);
        mgr.set_enabled(false);
        assert!(!mgr.should_block_host("b.ads.com"), "禁用时不拦截");
        assert_eq!(mgr.total_blocked(), 1, "禁用路径不计数");
    }

    #[test]
    fn manager_implements_debug() {
        // RS-068：AdBlockManager 可 Debug 格式化（诊断/日志面）
        let mgr = AdBlockManager::new();
        let rendered = format!("{mgr:?}");
        assert!(rendered.contains("AdBlockManager"));
        assert!(rendered.contains("total_blocked"));
    }
}

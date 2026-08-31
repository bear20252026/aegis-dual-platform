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
    pub fn should_block(&mut self, url: &str) -> bool {
        if !self.is_enabled {
            return false;
        }
        if let Some(host) = Self::extract_host(url) {
            if self.blocked_domains.contains(&host) {
                self.total_blocked += 1;
                return true;
            }
            // H-8 修复（审计 2026-08-31）：父域迭代匹配——原实现是
            // host.split('.') 逐「单段」精确比对（ads.example.com 会拿
            // ads/example/com 三个单词查表），黑名单含常见单词域即大面积
            // 误拦、两段父域（ads.com）永远无法命中。改为逐级剥去最左
            // 标签：a.ads.com → ads.com → com（真正的父域链检查）。
            let mut host = host.as_str();
            while let Some((_, rest)) = host.split_once('.') {
                host = rest;
                if self.blocked_domains.contains(host) {
                    self.total_blocked += 1;
                    return true;
                }
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
}

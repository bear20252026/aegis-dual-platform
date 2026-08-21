/*
 * adblock.rs — 广告/追踪拦截器（照搬 Omni Browser AdBlockManager.kt 本地化适配）。
 *
 * 原始版权：Omni Browser - Copyright (C) 2026 RebelRoot Ltd
 * 原始许可：GNU General Public License v3.0
 * 来源：https://github.com/REBEL-ROOT/omni-browser
 * 改动：将 Kotlin 实现翻译为 Rust，适配 Aegis 架构（无 Android 依赖）。
 */

use std::collections::{HashMap, HashSet};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

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
            // 检查父域名（example.ads.com → ads.com）
            for part in host.split('.') {
                let domain = part.to_string();
                if self.blocked_domains.contains(&domain) {
                    self.total_blocked += 1;
                    return true;
                }
            }
        }
        false
    }

    /// 从 URL 提取主机名。
    fn extract_host(url: &str) -> Option<String> {
        let without_scheme = url.strip_prefix("https://")
            .or_else(|| url.strip_prefix("http://"))
            .unwrap_or(url);
        without_scheme.split('/').next().map(|h| h.to_lowercase())
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
}

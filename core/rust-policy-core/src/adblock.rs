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
///
/// RS-265（2026-10-01 审计）：`rule_count`/`last_updated` 字段已删除——
/// 此前恒为 0 且 core 无任何回写路径（filter list 的下载/解析/计数是宿主
/// 职责，core 只消费 `load_blocked_domains` 注入的归一化 host 集），
/// 常驻的假数据只会让 UI 展示面失真。宿主需要展示规则数/更新时间时在
/// 自己的下载层维护（单一事实源），不得在此重新声明。
#[derive(Debug, Clone)]
pub struct AdBlockProvider {
    pub id: String,
    pub name: String,
    pub url: String,
    pub is_preset: bool,
    pub is_enabled: bool,
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
            },
            AdBlockProvider {
                id: "adguard_base".into(),
                name: "AdGuard Base Filter".into(),
                url: "https://filters.adtidy.org/extension/ublock/filters/2.txt".into(),
                is_preset: true,
                is_enabled: true,
            },
            AdBlockProvider {
                id: "adguard_anti_adblock".into(),
                name: "AdGuard Anti-AdBlock Defusers".into(),
                url: "https://filters.adtidy.org/extension/ublock/filters/14.txt".into(),
                is_preset: true,
                is_enabled: true,
            },
            AdBlockProvider {
                id: "peter_lowe".into(),
                name: "Peter Lowe's Ad & Tracker List".into(),
                url: "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=hosts&showintro=0&mimetype=plaintext".into(),
                is_preset: true,
                is_enabled: true,
            },
            AdBlockProvider {
                id: "fanboy_social".into(),
                name: "Fanboy Social Tracking Blocker".into(),
                url: "https://easylist.to/easylist/fanboy-social.txt".into(),
                is_preset: true,
                is_enabled: true,
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
    ///
    /// RS-179（审计 2026-09-25）：入库归一——黑名单条目与查询侧
    /// （should_block_host）的归一口径对齐（ASCII 小写、剥尾点）。此前
    /// 按字面入库，`Ads.Example.COM` 之类条目永远无法命中（查询侧已
    /// 归一）——**fail-open 方向**：看起来已拦截实际放行。RS-180：空串
    /// 与归一后为空的条目不入库（空键会被无 host 形态意外命中）。
    /// 审计第六轮（2026-10-03）：入库折叠改调 util::normalize_host_key
    /// 单源——此前本处与查询侧各写一份归一（本处剥尾点、extract_host
    /// 不剥），两侧永远对不齐（尾点查询漏拦）。
    pub fn load_blocked_domains(&mut self, domains: impl IntoIterator<Item = String>) {
        let normalized = domains.into_iter().filter_map(|d| {
            // RS-283（2026-10-02 审计）：入库折叠 ASCII 口径（host 匹配域
            // 是 DNS 语义）——归一单源后与查询侧同函数，不再分叉
            crate::util::normalize_host_key(d.trim())
        });
        self.blocked_domains.extend(normalized);
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
    ///
    /// 审计第六轮（2026-10-03）：host 解析失败由「不拦截」改为**拦截**——
    /// 此前 `extract_host` 返回 None 即 `false`，畸形/无法解析的 URL 一律
    /// 放行（黑名单是 denylist，提取失败不是「不在名单上」的证据，而是
    /// 「无法证明不在名单上」）。禁用态（is_enabled=false）是用户显式
    /// 关闭拦截，仍整体放行——解析失败不越过显式开关。
    pub fn should_block(&mut self, url: &str) -> bool {
        if !self.is_enabled {
            return false;
        }
        match Self::extract_host(url) {
            Some(host) => self.should_block_host(&host),
            None => {
                self.total_blocked += 1;
                true // fail-closed：解析失败按拦截处理
            }
        }
    }

    /// 检查已归一化（小写、无端口、无 userinfo）的主机名是否应被拦截。
    ///
    /// RS-069（审计 2026-09-25）预归一 API：调用方绕过 URL 解析与
    /// to_lowercase 分配；语义与 [`AdBlockManager::should_block`]
    /// 完全一致（含父域链迭代与命中计数）。
    /// 审计第六轮（2026-10-03）：口径边界补充——「完全一致」指**已归一
    /// host 的匹配语义**一致；fail-closed（解析失败即拦截）只发生在
    /// [`AdBlockManager::should_block`] 的 URL 解析面。本 API 的入参由调用方
    /// 保证已归一（空串等非法键只可能精确命中同名条目，不做解析失败推断）。
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
    fn malformed_urls_fail_closed_as_blocked() {
        // RS-065 + 审计第六轮（2026-10-03）：畸形 URL 不 panic；语义由
        // 「不拦截」改为**拦截**——denylist 遇到无法解析的 host 时，
        // 「提取失败」不等于「不在名单上」（此前 None → false 即 fail-open：
        // 把 URL 写成畸形形态即可绕过整张黑名单）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        for malformed in ["", "https://", "2001:db8::1", "https://[unclosed/x"] {
            assert!(
                mgr.should_block(malformed),
                "解析失败必须 fail-closed 拦截：{malformed:?}"
            );
        }
        assert_eq!(mgr.total_blocked(), 4, "fail-closed 拦截同样计数");
        // 显式禁用是用户关闭拦截——解析失败不越过该开关
        mgr.set_enabled(false);
        assert!(!mgr.should_block(""), "禁用态整体放行");
        assert!(!mgr.should_block("https://ads.example.com/x"), "禁用态放行");
    }

    #[test]
    fn query_side_trailing_dot_hits_normalized_entry() {
        // 审计第六轮（2026-10-03）：入库剥尾点而查询侧不剥——同一 host 的
        // 两种拼写只有归一后才是同一个键（查询侧现共用 normalize_host_key）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["tracker.org".into()]);
        assert!(
            mgr.should_block("https://tracker.org./ad.js"),
            "查询侧尾点必须与入库条目对齐"
        );
        assert!(
            mgr.should_block("https://TRACKER.ORG./ad.js"),
            "大写 + 尾点同批归一"
        );
        // 父域链在归一后的 host 上仍成立（剥尾点不影响逐级剥标签）
        assert!(mgr.should_block("https://cdn.tracker.org./ad.js"));
    }

    #[test]
    fn parent_chain_probe_survives_normalization() {
        // 审计第六轮（2026-10-03）：新增「解析失败 fail-closed」不得吃掉
        // 父域链正常路径——三级子域对两段父域 / 对 TLD 条目均命中
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(["ads.com".into(), "net".into()]);
        assert!(mgr.should_block("https://a.b.ads.com/x"), "两段父域命中");
        assert!(mgr.should_block("https://x.y.example.NET/"), "TLD 条目命中");
        assert!(
            !mgr.should_block("https://a.b.example.com/x"),
            "未登记域不误拦（解析成功路径不被 fail-closed 波及）"
        );
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

    // —— RS-179/180（审计 2026-09-25）：入库归一与条目卫生 ——

    #[test]
    fn loaded_domains_normalized_case_and_trailing_dot() {
        // RS-179：黑名单条目此前按字面入库——大小写变体/尾点形式与查询侧
        // （已归一）永不相等，条目形同虚设（fail-open）。入库归一后命中
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(["Ads.Example.COM".to_string(), "tracker.org.".to_string()]);
        assert!(
            mgr.should_block("https://ads.example.com/x"),
            "大小写变体入库后必须命中"
        );
        assert!(
            mgr.should_block("https://tracker.org/ad.js"),
            "尾点条目归一后必须命中"
        );
        assert!(
            mgr.should_block("https://ADS.EXAMPLE.COM/"),
            "查询侧大写变体命中"
        );
        assert!(!mgr.should_block("https://clean.example.org/"));
    }

    #[test]
    fn empty_and_blank_entries_rejected_at_load() {
        // RS-180：空串/纯空白/纯尾点条目不入库——空键会被无 host 形态
        // 意外命中（若入库则 should_block("") 形态语义被污染）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains([
            String::new(),
            "   ".to_string(),
            ".".to_string(),
            "real.example".to_string(),
        ]);
        assert!(!mgr.should_block_host(""), "空键不得入库");
        assert_eq!(mgr.total_blocked, 0, "无条目应被命中");
        assert!(mgr.should_block("https://real.example/"));
    }

    #[test]
    fn duplicate_entries_are_idempotent() {
        // RS-180：重复条目幂等（HashSet 语义）——计数不受重复加载影响
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(["dup.com".to_string(), "dup.com".to_string()]);
        mgr.load_blocked_domains(["dup.com".to_string()]);
        assert!(mgr.should_block("https://dup.com/"));
        assert_eq!(mgr.total_blocked, 1, "重复入库不放大命中计数");
    }

    // —— RS-275 回归（2026-10-02）：userinfo 双 @ 不得漏拦 ——

    #[test]
    fn userinfo_with_embedded_at_still_blocks() {
        // RS-275：`https://x@evil@ads.example.com/` 此前 extract_host 取
        // 首个 @，host 被提取为 "evil@ads.example.com"（带前缀）——黑名单
        // ads.example.com 永不命中（漏拦）。统一取最后一个 @ 后命中
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains(vec!["ads.example.com".into()]);
        assert!(
            mgr.should_block("https://x@evil@ads.example.com/"),
            "双 @ userinfo 形态必须仍按真实 host 拦截"
        );
        assert!(
            mgr.should_block("https://a@b@ads.example.com/banner"),
            "a@b@blocked.host 向量"
        );
    }

    // —— RS-283 回归（2026-10-02）：入库与查询侧折叠口径一致 ——

    #[test]
    fn non_ascii_entries_fold_ascii_like_query_side() {
        // RS-283：非 ASCII 条目入库与查询侧（to_ascii_lowercase）同口径——
        // 此前 Unicode 折叠把 İ 变 "i"+U+0307，条目永不命中（fail-open）
        let mut mgr = AdBlockManager::new();
        mgr.load_blocked_domains([
            "İstanbul.example".to_string(),
            "Ads.XN--EXAMPLE".to_string(),
        ]);
        // 查询侧 ASCII 折叠保留非 ASCII 字符原样 → 与入库键相等 → 命中
        assert!(
            mgr.should_block("https://İstanbul.example/"),
            "非 ASCII 条目必须可命中（双侧同 ASCII 折叠）"
        );
        assert!(
            mgr.should_block("https://ads.xn--example/"),
            "纯 ASCII 折叠行为不变"
        );
        // Unicode 折叠特有形态不得出现：入库键不得是 "i̇stanbul..."（i+U+0307）
        assert!(
            !mgr.should_block_host("i̇stanbul.example"),
            "Unicode 折叠形态不是入库键"
        );
    }
}

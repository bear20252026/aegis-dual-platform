//! 威胁 host 黑名单快照（FfiBroker 的生产子模块，非测试模块）。
//!
//! 审计第六轮（2026-10-03/04）：deny-by-content 首次在 FFI 通路生效——此前
//! H-7 注记明载「policy.evaluate / capability.validate 未接入 FFI 通路」，
//! `evaluate_navigation` 的拒绝条件只有"URL 是否良构"，任意良构 https URL
//! 一律 Allow（恶意 host 不例外）。黑名单此前只活在两端宿主代码里，Android
//! 端因此整体没有威胁拦截。
//!
//! 审计第七轮（2026-10-04）R7-RS-01/R7-RS-02：匹配口径与注入规模各自收口，
//! 本模块自 `ffi/broker.rs` 抽出（行数红线 + 单一职责）。
//!
//! **空集合 = 不拦**（默认绝不 deny-all）：未接入订阅源的端行为与既往完全
//! 一致，这是本能力能安全落地的前提。

/// 威胁 host 黑名单快照。条目由宿主（订阅源）注入，判定发生在导航的
/// evaluate 与 consume 两点（同一入口，见 `host_denied`）。
#[derive(Default)]
pub(crate) struct HostDenylist {
    entries: std::sync::Mutex<std::collections::HashSet<String>>,
}

/// 黑名单条目 host 形态校验——与 `canonicalize_external` 的 host 口径一致。
/// 尾点/前导点/空段/越界字符的条目永远不会被命中，收下即制造"已登记但永不生效"
/// 的死条目（比不登记更坏：订阅源看起来是工作的）。
fn entry_shape_ok(host: &str) -> bool {
    !host.is_empty()
        && !host.starts_with('.')
        && !host.ends_with('.')
        && !host.contains("..")
        && host
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
}

impl HostDenylist {
    /// 命中判定：**精确 + 逐后缀剥左标签**（父域语义）。
    ///
    /// R7-RS-01（审计第七轮 2026-10-04）：此前是 `entries.contains(host)`
    /// 精确匹配，订阅源以裸域登记的条目在核心侧只封字面那一条，
    /// `www.`/`api.`/任意子域全部放行——而孪生实现（同仓
    /// `adblock::should_block_host`、Windows `ThreatFeed.IsBlocked`、
    /// Python `threat_feed.py`）都是"精确 + 逐后缀"。现对齐同一口径：
    /// `x.bad.example` → `bad.example` → `example`（每剥一个左标签查一次表）。
    ///
    /// 展开**只发生在查询侧**：绝不得把清单条目的祖先域预展开入表——
    /// 登记 `evil.example.com` 若连带封掉 `example.com`/`com` 就是过度封锁
    ///（Windows `ThreatFeed.cs:44-46` 明载首版实现即此缺陷，单测拦截后改本版；
    /// 向量 `R7_RS_01_entry_ancestors_are_not_pre_expanded` 在核心侧钉同一条）。
    ///
    /// 锁中毒按**被拒**处理——黑名单是拦截面，判定失败绝不 fail-open。
    pub(crate) fn host_denied(&self, host: &str) -> bool {
        let Ok(entries) = self.entries.lock() else {
            return true;
        };
        if entries.contains(host) {
            return true;
        }
        // 逐级剥去最左标签：a.ads.com → ads.com → com（真正的父域链检查）
        let mut suffix = host;
        while let Some((_, rest)) = suffix.split_once('.') {
            suffix = rest;
            if entries.contains(suffix) {
                return true;
            }
        }
        false
    }

    /// 注入一批条目，返回**本批被接受**的条目数（调用方可用
    /// `输入数 - 返回值` 发现有一批条目被形态校验拒收，而不是静默变成死条目；
    /// 追加模式下返回值同样只计本批，不计并集——重复推送同批条目不会虚报为 0）。
    ///
    /// R7-RS-02（审计第七轮 2026-10-04）：`clear` 两阶段。真实订阅源远大于
    /// 单次 FFI 载荷上限（`c_abi` 的 `FFI_INPUT_MAX_BYTES` = 64KiB，而托管侧
    /// 允许 5 MiB 源），整批替换在真实规模下必然注入失败 → 核心侧
    /// `threat_blocklist` 分支实际从不执行。故宿主可分块推送：首块
    /// `clear = true`（先清空再接受本批），后续 `clear = false`（追加）。
    ///
    /// 空输入 + `clear = true` = 清空（**不** deny-all）；空输入 +
    /// `clear = false` = 无操作（保留既有快照）。
    /// 锁中毒：不改动快照（保留旧快照比清空/半写安全），如实报 0 接受。
    pub(crate) fn apply(&self, hosts: Vec<String>, clear: bool) -> u32 {
        let accepted: std::collections::HashSet<String> = hosts
            .into_iter()
            .map(|host| host.trim().to_ascii_lowercase())
            .filter(|host| entry_shape_ok(host))
            .collect();
        let count = accepted.len() as u32;
        match self.entries.lock() {
            Ok(mut entries) => {
                if clear {
                    *entries = accepted;
                } else {
                    entries.extend(accepted);
                }
            }
            Err(_) => return 0,
        }
        count
    }
}

#[cfg(test)]
mod tests {
    use super::HostDenylist;

    /// 锁中毒的两个 fail-closed 口径（第七轮 R7-RS-01 硬约束，此前全仓零锚点）：
    /// 判定侧按**被拒**处理（黑名单是拦截面，绝不 fail-open）；注入侧不得在
    /// 中毒锁上声称「已接受」（保留旧快照比清空/半写安全，如实报 0）。
    #[test]
    fn poisoned_lock_denies_lookup_and_claims_no_injection() {
        let denylist = HostDenylist::default();
        assert_eq!(denylist.apply(vec!["bad.example".into()], true), 1);
        {
            let guard = denylist
                .entries
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let _held = guard; // panic 时随栈展开 drop 守卫 → 锁进入中毒态
                panic!("intentional denylist lock poisoning");
            }));
        }
        assert!(
            denylist.host_denied("never-listed.example"),
            "中毒锁必须按被拒处理，不得 fail-open"
        );
        assert_eq!(
            denylist.apply(vec!["other.example".into()], true),
            0,
            "中毒锁不得虚报已注入"
        );
        // 反向对照：未中毒时同一入口一切正常（防「改成恒拒」式假闭环）
        let healthy = HostDenylist::default();
        healthy.apply(vec!["ok.example".into()], true);
        assert!(!healthy.host_denied("fine.example"));
    }
}

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
//! 第八轮 ⑨（R8-RS-14，用户 2026-10-07 定稿）：**分批推送期间不再被读到**。
//! 此前首批 `clear=1` 立即清空活动快照、只装入第一批 ⇒ 5 MiB 规模下约 85 批
//! 的推送窗口内，导航判定读的是**不完整**名单（未推到的恶意 host 直接 Allow）；
//! 任一批失败则核心永久保留前缀，而判定侧没有任何世代/完整标记可分辨
//! 「完整快照」与「残缺前缀」。现改为暂存 + 原子提交（见 `MODE_BEGIN`/`MODE_COMMIT`）。
//!
//! **空集合 = 不拦**（默认绝不 deny-all）：未接入订阅源的端行为与既往完全
//! 一致，这是本能力能安全落地的前提。

use super::FfiBroker;
use std::collections::HashSet;
use std::sync::Mutex;

/// 注入档位——即 C ABI 第三个参数 `clear` 的取值域。
///
/// 0/1 是既往语义（追加 / 整批替换活动快照），**未改一字**：只发 0/1 的旧宿主
/// 行为逐字不变，这是本改动能安全落地的前提。2/3 是 ⑨ 新增的会话档位。
pub(crate) const MODE_APPEND: i32 = 0;
pub(crate) const MODE_REPLACE: i32 = 1;
/// 开一次分批会话：本批进**暂存**，活动快照不动，判定继续读上一份完整快照。
pub(crate) const MODE_BEGIN: i32 = 2;
/// 提交会话：暂存整体原子换为活动快照。中途任何一批失败就不必提交——
/// 下一次 `MODE_BEGIN` 会丢弃旧暂存，活动快照始终是一份完整的名单。
pub(crate) const MODE_COMMIT: i32 = 3;

/// 威胁 host 黑名单快照。条目由宿主（订阅源）注入，判定发生在导航的
/// evaluate 与 consume 两点（同一入口，见 `host_denied`）。
#[derive(Default)]
pub(crate) struct HostDenylist {
    state: Mutex<Snapshot>,
}

#[derive(Default)]
struct Snapshot {
    /// 判定读的这一份——只在 `MODE_REPLACE` 或 `MODE_COMMIT` 时整体更换。
    active: HashSet<String>,
    /// 分批会话的暂存区；`None` = 无会话（此时 `MODE_APPEND` 按既往直接追加活动快照）。
    staging: Option<HashSet<String>>,
}

/// 一次注入的应答。`accepted` 是本批被接受的条目数（形态校验拒收的差额由宿主
/// 用 `input - accepted` 发现），`staged` 应答「本批之后是否仍有未提交的会话」，
/// `served` 是判定侧此刻实际读到的条目数——宿主据此能在日志里区分「推完了」与
/// 「提交了」，而不是靠批数猜。
pub(crate) struct ApplyReport {
    pub(crate) accepted: u32,
    pub(crate) mode: i32,
    pub(crate) staged: bool,
    pub(crate) served: u32,
}

impl ApplyReport {
    /// 锁中毒/未知档位：什么都不改，如实报 0 接受（宿主据此判失败，不会误认为已生效）。
    fn refused(mode: i32, served: u32) -> Self {
        Self {
            accepted: 0,
            mode,
            staged: false,
            served,
        }
    }
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

/// 档位是否在已知集合内。未知档位一律拒收而不是"当作 0 处理"：静默 reinterpret
/// 会让下一版新增档位时把旧核心的行为错认成新行为。
pub(crate) fn mode_is_known(mode: i32) -> bool {
    matches!(mode, MODE_APPEND | MODE_REPLACE | MODE_BEGIN | MODE_COMMIT)
}

impl HostDenylist {
    /// 判定只看活动快照——**暂存区永不参与判定**（⑨ 的全部意义）。
    ///
    /// R7-RS-01（审计第七轮 2026-10-04）：此前是 `entries.contains(host)`
    /// 精确匹配，订阅源以裸域登记的条目在核心侧只封字面那一条，`www.`/`api.`
    /// 及任意子域全部放行——而孪生实现（同仓 `adblock::should_block_host`、
    /// Windows `ThreatFeed.IsBlocked`、Python `threat_feed.py`）都是
    /// "精确 + 逐后缀"。现对齐同一口径：`x.bad.example` → `bad.example` →
    /// `example`（每剥一个左标签查一次表）。
    ///
    /// 展开**只发生在查询侧**：绝不得把清单条目的祖先域预展开入表——登记
    /// `evil.example.com` 若连带封掉 `example.com`/`com` 就是过度封锁
    ///（Windows `ThreatFeed.cs:44-46` 明载首版实现即此缺陷，单测拦截后改本版；
    /// 向量 `R7_RS_01_entry_ancestors_are_not_pre_expanded` 在核心侧钉同一条）。
    ///
    /// 锁中毒按**被拒**处理——黑名单是拦截面，判定失败绝不 fail-open。
    pub(crate) fn host_denied(&self, host: &str) -> bool {
        let Ok(snapshot) = self.state.lock() else {
            return true;
        };
        let entries = &snapshot.active;
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

    /// 当前判定侧读到的条目数（锁中毒按 0 报——只用于日志，不参与判定）。
    pub(crate) fn served_count(&self) -> u32 {
        self.state
            .lock()
            .map(|snapshot| snapshot.active.len() as u32)
            .unwrap_or(0)
    }

    /// 注入一批条目。档位语义见 `MODE_*`；返回值见 [`ApplyReport`]。
    ///
    /// R7-RS-02（审计第七轮 2026-10-04）：真实订阅源远大于单次 FFI 载荷上限
    ///（`c_abi` 的 `FFI_INPUT_MAX_BYTES` = 64KiB，而托管侧允许 5 MiB 源），
    /// 整批替换在真实规模下必然注入失败 → 核心侧 `threat_blocklist` 分支实际
    /// 从不执行。故宿主可分块推送。
    ///
    /// ⑨（第八轮）把「分批」与「换快照」分开：`MODE_BEGIN`/`MODE_APPEND` 只动
    /// 暂存，`MODE_COMMIT` 才整体换掉活动快照。会话未开时 `MODE_APPEND` 仍是
    /// 既往的"追加到活动快照"（旧宿主逐字不变）；`MODE_REPLACE` 会顺带丢弃
    /// 未提交的暂存（它表达的是一次整批替换，留着半截会话更糟）。
    ///
    /// 空输入 + `MODE_REPLACE` = 清空（**不** deny-all）；空输入 +
    /// `MODE_APPEND` = 无操作；空输入 + `MODE_BEGIN` = 开一次「将提交空名单」的会话。
    /// 锁中毒：不改动快照（保留旧快照比清空/半写安全），如实报 0 接受。
    pub(crate) fn apply(&self, hosts: Vec<String>, mode: i32) -> ApplyReport {
        if !mode_is_known(mode) {
            return ApplyReport::refused(mode, self.served_count());
        }
        let accepted: HashSet<String> = hosts
            .into_iter()
            .map(|host| host.trim().to_ascii_lowercase())
            .filter(|host| entry_shape_ok(host))
            .collect();
        let count = accepted.len() as u32;
        let Ok(mut snapshot) = self.state.lock() else {
            return ApplyReport::refused(mode, 0);
        };
        let mut committed = false;
        let staged = match mode {
            MODE_BEGIN => {
                snapshot.staging = Some(accepted);
                true
            }
            MODE_APPEND => {
                match &mut snapshot.staging {
                    Some(pending) => pending.extend(accepted),
                    // 旧宿主（从未 begin）⇒ 追加仍进活动快照，语义逐字不变
                    None => snapshot.active.extend(accepted),
                }
                snapshot.staging.is_some()
            }
            MODE_REPLACE => {
                snapshot.staging = None;
                snapshot.active = accepted;
                false
            }
            _ => {
                // MODE_COMMIT：无会话可提交时什么都不换（活动快照保持上一份完整名单）
                if let Some(pending) = snapshot.staging.take() {
                    snapshot.active = pending;
                    committed = true;
                }
                false
            }
        };
        ApplyReport {
            // 提交档位不报条目数（那一数在 `served` 里），只报「这次提交换没换快照」——
            // 空名单的合法提交同样报 1，因为它确实把活动快照换成了空。
            accepted: if mode == MODE_COMMIT {
                u32::from(committed)
            } else {
                count
            },
            mode,
            staged,
            served: snapshot.active.len() as u32,
        }
    }
}

// 审计第六轮（deny-by-content 接入 FFI）与第八轮 ⑨（档位化）：FfiBroker 上的
// 注入口。放在本模块而不是 broker.rs——后者在 940 行零余量基线上，且档位语义
// 与快照状态是一体，测试也在同一旁边。跨语言面只在 C ABI（`c_abi::navigation`）：
// UniFFI 绑定面维持 `update_host_denylist`（整批替换）不变、不新增导出项
//（生成绑定的滞后另有第七轮 R7-RS-03 登记）。
impl FfiBroker {
    /// 黑名单快照注入的 Rust 侧单点（R7-RS-02 清空/追加两阶段的兼容入口）。
    pub(crate) fn apply_host_denylist(&self, hosts: Vec<String>, clear: bool) -> u32 {
        self.apply_host_denylist_mode(hosts, if clear { MODE_REPLACE } else { MODE_APPEND })
            .accepted
    }

    /// ⑨（第八轮 R8-RS-14）：`clear` 参数已扩成**档位**（0 追加 / 1 整批替换 /
    /// 2 开分批会话 / 3 提交会话）。旧宿主只发 0/1，走的仍是既往路径。
    pub(crate) fn apply_host_denylist_mode(&self, hosts: Vec<String>, mode: i32) -> ApplyReport {
        self.deny_hosts.apply(hosts, mode)
    }
}

#[cfg(test)]
mod tests;

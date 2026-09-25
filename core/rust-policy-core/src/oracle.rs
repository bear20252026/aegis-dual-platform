//! Oracle（照搬 fieldpass/picket Oracle 确定性回放验证）。
//!
//! 对已执行的副作用进行 snapshot/diff/verify（确定性——无 LLM），
//! 确保每次执行的结果可重现、可审计。
//!
//! 职责：
//! - 快照（snapshot）：记录副作用执行前后的状态
//! - 差异（diff）：比较预期与实际结果
//! - 验证（verify）：确定性校验（无 LLM——纯规则）
//!
//! 可拆卸：本模块不依赖 UI/网络/策略引擎。
//! 可拼接：通过 `AuditEvent` 与 executor/audit 层对接。

use std::collections::{HashMap, VecDeque};
use std::time::Instant;

/// 快照记录（副作用执行前后的状态）。
#[derive(Debug, Clone)]
pub struct Snapshot {
    pub action_id: String,
    pub session_id: String,
    pub captured_at: Instant,
    pub state_before: HashMap<String, String>,
    pub state_after: HashMap<String, String>,
}

/// 差异报告（预期 vs 实际）。
#[derive(Debug, Clone)]
pub struct DiffReport {
    pub action_id: String,
    pub mismatches: Vec<Mismatch>,
    pub verdict: VerifyVerdict,
}

/// 单个不匹配项。
#[derive(Debug, Clone)]
pub struct Mismatch {
    pub field: String,
    pub expected: String,
    pub actual: String,
}

/// 验证结论（确定性——无 LLM）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerifyVerdict {
    /// 预期与实际一致（通过）。
    Pass,
    /// 存在差异但可接受（警告）。
    Warning(String),
    /// 预期与实际不一致（失败）。
    Fail(String),
}

/// Oracle——确定性回放验证器（照搬 picket Oracle）。
///
/// RS-102（审计 2026-09-25）：有界保留容器改 `VecDeque`——此前
/// `Vec::remove(0)` 每次逐出 O(n) 全员搬移；VecDeque pop_front O(1)。
#[derive(Debug)]
pub struct Oracle {
    snapshots: VecDeque<Snapshot>,
    reports: VecDeque<DiffReport>,
}

/// 有界保留上限——防长期运行无界内存增长。
const MAX_RETAINED: usize = 1000;

impl Default for Oracle {
    fn default() -> Self {
        Self::new()
    }
}

impl Oracle {
    pub fn new() -> Self {
        Self {
            snapshots: VecDeque::new(),
            reports: VecDeque::new(),
        }
    }

    /// 记录快照（副作用执行前/后状态）。有界保留（接入生产路径不再无界增长）。
    pub fn snapshot(&mut self, snap: Snapshot) {
        if self.snapshots.len() >= MAX_RETAINED {
            self.snapshots.pop_front();
        }
        self.snapshots.push_back(snap);
    }

    /// 验证快照（确定性规则——无 LLM）。任何不匹配即 Fail（fail-closed）。
    pub fn verify(&mut self, snap: &Snapshot) -> DiffReport {
        self.verify_with_warn_fields(snap, &[])
    }

    /// RS-101（审计 2026-09-25）：`Warning` 变体的唯一合法构造点——
    /// 调用方显式声明「允许漂移」的字段（如天然不稳定的 timestamp 类），
    /// 不匹配全部落在白名单内 → Warning（可接受差异，仍留 mismatch 记录）；
    /// 白名单外任一字段不匹配 → Fail。默认 `verify` 白名单为空——
    /// 不匹配一律 Fail，口径不变。
    pub fn verify_with_warn_fields(&mut self, snap: &Snapshot, warn_fields: &[&str]) -> DiffReport {
        let mut mismatches = Vec::new();

        // 逐字段比较（state_before vs state_after）
        for (key, before_val) in &snap.state_before {
            match snap.state_after.get(key) {
                Some(after_val) => {
                    if before_val != after_val {
                        mismatches.push(Mismatch {
                            field: key.clone(),
                            expected: before_val.clone(),
                            actual: after_val.clone(),
                        });
                    }
                }
                None => {
                    mismatches.push(Mismatch {
                        field: key.clone(),
                        expected: before_val.clone(),
                        actual: "<missing>".into(),
                    });
                }
            }
        }

        // RS-032（审计 2026-09-24）：after 新增键此前不可检测——副作用若
        // 注入新状态字段（如自增计数器/新窗口句柄）即静默通过
        for key in snap.state_after.keys() {
            if !snap.state_before.contains_key(key) {
                mismatches.push(Mismatch {
                    field: key.clone(),
                    expected: "<absent>".into(),
                    actual: snap.state_after[key].clone(),
                });
            }
        }

        // 确定性结论——不匹配一律 Fail（此前 expected 值以 "safe_" 开头即降级
        // Warning 放行：攻击者可控状态字段命名 = fail-open 后门）。
        // RS-101：仅调用方显式声明的 warn_fields 内的不匹配才降级 Warning
        let verdict = if mismatches.is_empty() {
            VerifyVerdict::Pass
        } else if mismatches
            .iter()
            .all(|m| warn_fields.contains(&m.field.as_str()))
        {
            VerifyVerdict::Warning(format!("{} 个字段漂移（均在允许列表内）", mismatches.len()))
        } else {
            VerifyVerdict::Fail(format!("{} 个字段不匹配", mismatches.len()))
        };

        let report = DiffReport {
            action_id: snap.action_id.clone(),
            mismatches,
            verdict,
        };
        if self.reports.len() >= MAX_RETAINED {
            self.reports.pop_front();
        }
        self.reports.push_back(report.clone());
        report
    }

    /// 获取所有验证报告。
    pub fn reports(&self) -> &VecDeque<DiffReport> {
        &self.reports
    }

    /// 获取所有快照。
    pub fn snapshots(&self) -> &VecDeque<Snapshot> {
        &self.snapshots
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_snapshot(
        action: &str,
        before: Vec<(&str, &str)>,
        after: Vec<(&str, &str)>,
    ) -> Snapshot {
        Snapshot {
            action_id: action.into(),
            session_id: "s1".into(),
            captured_at: Instant::now(),
            state_before: before
                .into_iter()
                .map(|(k, v)| (k.into(), v.into()))
                .collect(),
            state_after: after
                .into_iter()
                .map(|(k, v)| (k.into(), v.into()))
                .collect(),
        }
    }

    #[test]
    fn identical_snapshot_passes() {
        let mut oracle = Oracle::new();
        let snap = make_snapshot(
            "a1",
            vec![("status", "ok"), ("count", "5")],
            vec![("status", "ok"), ("count", "5")],
        );
        let report = oracle.verify(&snap);
        assert_eq!(report.verdict, VerifyVerdict::Pass);
        assert!(report.mismatches.is_empty());
    }

    #[test]
    fn changed_field_detected() {
        let mut oracle = Oracle::new();
        let snap = make_snapshot("a2", vec![("status", "ok")], vec![("status", "modified")]);
        let report = oracle.verify(&snap);
        assert!(matches!(report.verdict, VerifyVerdict::Fail(_)));
        assert_eq!(report.mismatches.len(), 1);
    }

    #[test]
    fn missing_field_detected() {
        let mut oracle = Oracle::new();
        let snap = make_snapshot("a3", vec![("key", "val")], vec![]);
        let report = oracle.verify(&snap);
        assert!(matches!(report.verdict, VerifyVerdict::Fail(_)));
        assert_eq!(report.mismatches[0].actual, "<missing>");
    }

    #[test]
    fn after_added_key_detected() {
        // RS-032 回归：after 新增键必须产出 Mismatch——此前只遍历 before，
        // 副作用注入新状态字段（新计数器/句柄）静默通过
        let mut oracle = Oracle::new();
        let snap = make_snapshot(
            "a4",
            vec![("status", "ok")],
            vec![("status", "ok"), ("injected_counter", "1")],
        );
        let report = oracle.verify(&snap);
        assert!(matches!(report.verdict, VerifyVerdict::Fail(_)));
        assert_eq!(report.mismatches.len(), 1);
        assert_eq!(report.mismatches[0].field, "injected_counter");
        assert_eq!(report.mismatches[0].expected, "<absent>");
        assert_eq!(report.mismatches[0].actual, "1");
    }

    #[test]
    fn reports_accumulate() {
        let mut oracle = Oracle::new();
        let s1 = make_snapshot("a1", vec![], vec![]);
        let s2 = make_snapshot("a2", vec![], vec![]);
        oracle.verify(&s1);
        oracle.verify(&s2);
        assert_eq!(oracle.reports().len(), 2);
    }

    // —— RS-100/101 回归（审计 2026-09-25） ——

    #[test]
    fn snapshot_and_reports_bounded_fifo() {
        // RS-100：有界保留——超上限后 FIFO 逐出最旧（内存不无界增长）
        let mut oracle = Oracle::new();
        for i in 0..MAX_RETAINED + 50 {
            oracle.snapshot(make_snapshot(&format!("s{i}"), vec![], vec![]));
            let snap = make_snapshot(&format!("r{i}"), vec![], vec![]);
            oracle.verify(&snap);
        }
        assert_eq!(oracle.snapshots().len(), MAX_RETAINED);
        assert_eq!(oracle.reports().len(), MAX_RETAINED);
        // FIFO 语义：最旧（s0/r0）已被逐出
        assert_eq!(oracle.snapshots().front().unwrap().action_id, "s50");
        assert_eq!(oracle.reports().front().unwrap().action_id, "r50");
    }

    #[test]
    fn multi_field_mismatch_counts_all() {
        // RS-100：多字段同时不匹配——计数完整（不短路漏报）
        let mut oracle = Oracle::new();
        let snap = make_snapshot(
            "multi",
            vec![("a", "1"), ("b", "2")],
            vec![("a", "x"), ("b", "y")],
        );
        let report = oracle.verify(&snap);
        match report.verdict {
            VerifyVerdict::Fail(msg) => assert!(msg.contains('2'), "{msg}"),
            other => panic!("期望 Fail，实际 {other:?}"),
        }
        assert_eq!(report.mismatches.len(), 2);
    }

    #[test]
    fn empty_snapshot_passes() {
        // RS-100：空 before/after——平凡通过
        let mut oracle = Oracle::new();
        let report = oracle.verify(&make_snapshot("empty", vec![], vec![]));
        assert_eq!(report.verdict, VerifyVerdict::Pass);
    }

    #[test]
    fn warning_only_for_declared_warn_fields() {
        // RS-101：Warning 变体构造单点——仅显式声明的允许漂移字段全部命中
        // 时降级 Warning；白名单外任一不匹配必须 Fail（fail-closed）
        let mut oracle = Oracle::new();
        let warn_snap = make_snapshot(
            "warn_ok",
            vec![("timestamp", "1"), ("status", "ok")],
            vec![("timestamp", "2"), ("status", "ok")],
        );
        let report = oracle.verify_with_warn_fields(&warn_snap, &["timestamp"]);
        assert!(
            matches!(report.verdict, VerifyVerdict::Warning(_)),
            "允许漂移字段全命中 → Warning"
        );
        // 混入白名单外的不匹配 → Fail
        let mixed = make_snapshot(
            "warn_mixed",
            vec![("timestamp", "1"), ("status", "ok")],
            vec![("timestamp", "2"), ("status", "changed")],
        );
        let report = oracle.verify_with_warn_fields(&mixed, &["timestamp"]);
        assert!(matches!(report.verdict, VerifyVerdict::Fail(_)));
        // 默认 verify 白名单为空——同输入 Fail（口径不回退）
        let strict = oracle.verify(&warn_snap);
        assert!(matches!(strict.verdict, VerifyVerdict::Fail(_)));
    }
}

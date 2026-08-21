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

use std::collections::HashMap;
use std::time::{Duration, Instant};

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
#[derive(Debug)]
pub struct Oracle {
    snapshots: Vec<Snapshot>,
    reports: Vec<DiffReport>,
}

impl Oracle {
    pub fn new() -> Self {
        Self {
            snapshots: Vec::new(),
            reports: Vec::new(),
        }
    }

    /// 记录快照（副作用执行前/后状态）。
    pub fn snapshot(&mut self, snap: Snapshot) {
        self.snapshots.push(snap);
    }

    /// 验证快照（确定性规则——无 LLM）。
    pub fn verify(&mut self, snap: &Snapshot) -> DiffReport {
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

        // 确定性结论
        let verdict = if mismatches.is_empty() {
            VerifyVerdict::Pass
        } else if mismatches.iter().all(|m| m.expected.starts_with("safe_")) {
            VerifyVerdict::Warning(format!("{} 个字段变化（安全范围内）", mismatches.len()))
        } else {
            VerifyVerdict::Fail(format!("{} 个字段不匹配", mismatches.len()))
        };

        let report = DiffReport {
            action_id: snap.action_id.clone(),
            mismatches,
            verdict,
        };
        self.reports.push(report.clone());
        report
    }

    /// 获取所有验证报告。
    pub fn reports(&self) -> &[DiffReport] {
        &self.reports
    }

    /// 获取所有快照。
    pub fn snapshots(&self) -> &[Snapshot] {
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
    fn reports_accumulate() {
        let mut oracle = Oracle::new();
        let s1 = make_snapshot("a1", vec![], vec![]);
        let s2 = make_snapshot("a2", vec![], vec![]);
        oracle.verify(&s1);
        oracle.verify(&s2);
        assert_eq!(oracle.reports().len(), 2);
    }
}

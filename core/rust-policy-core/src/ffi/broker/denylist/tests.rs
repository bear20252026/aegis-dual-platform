//! 黑名单快照的单元测试（⑨：暂存 + 提交协议的档位语义）。
//! 自 `denylist.rs` 外迁：那条文件按 300 行红线管理，而档位判据需要成组测试。

use super::{mode_is_known, HostDenylist, MODE_APPEND, MODE_BEGIN, MODE_COMMIT, MODE_REPLACE};

fn hosts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_string()).collect()
}

/// 锁中毒的两个 fail-closed 口径（第七轮 R7-RS-01 硬约束，此前全仓零锚点）：
/// 判定侧按**被拒**处理（黑名单是拦截面，绝不 fail-open）；注入侧不得在
/// 中毒锁上声称「已接受」（保留旧快照比清空/半写安全，如实报 0）。
#[test]
fn poisoned_lock_denies_lookup_and_claims_no_injection() {
    let denylist = HostDenylist::default();
    assert_eq!(
        denylist
            .apply(hosts(&["bad.example"]), MODE_REPLACE)
            .accepted,
        1
    );
    {
        let guard = denylist
            .state
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
        denylist
            .apply(hosts(&["other.example"]), MODE_REPLACE)
            .accepted,
        0,
        "中毒锁不得虚报已注入"
    );
    // 反向对照：未中毒时同一入口一切正常（防「改成恒拒」式假闭环）
    let healthy = HostDenylist::default();
    healthy.apply(hosts(&["ok.example"]), MODE_REPLACE);
    assert!(!healthy.host_denied("fine.example"));
}

/// ⑨ 的核心性质：**推送期间判定读的是上一份完整快照**，新条目要等提交才生效。
#[test]
fn staged_batches_are_invisible_to_adjudication_until_committed() {
    let denylist = HostDenylist::default();
    denylist.apply(hosts(&["old.example"]), MODE_REPLACE);

    let begin = denylist.apply(hosts(&["a.example"]), MODE_BEGIN);
    assert!(begin.staged, "begin 之后必须有未提交会话");
    assert_eq!(begin.served, 1, "begin 不得改动判定侧读到的快照");
    denylist.apply(hosts(&["b.example"]), MODE_APPEND);

    assert!(
        denylist.host_denied("old.example"),
        "提交前上一份快照必须继续生效（否则推送窗口就是放行窗口）"
    );
    assert!(
        !denylist.host_denied("a.example"),
        "暂存条目在提交前不得参与判定"
    );
    assert!(!denylist.host_denied("b.example"));
    assert_eq!(denylist.served_count(), 1);

    let commit = denylist.apply(hosts(&[]), MODE_COMMIT);
    assert_eq!(commit.accepted, 1, "accepted 报的是「这次换没换快照」");
    assert!(!commit.staged, "提交后会话关闭");
    assert_eq!(commit.served, 2, "换上来的是暂存那一份完整名单");
    assert!(denylist.host_denied("a.example") && denylist.host_denied("b.example"));
    assert!(
        !denylist.host_denied("old.example"),
        "提交是整体换，不是并集——旧条目必须随之退出"
    );
}

/// 半途而废的会话不会污染活动快照；下一次 begin 从头开始。
#[test]
fn abandoned_session_leaves_previous_snapshot_serving() {
    let denylist = HostDenylist::default();
    denylist.apply(hosts(&["keeper.example"]), MODE_REPLACE);

    denylist.apply(hosts(&["half-1.example"]), MODE_BEGIN);
    denylist.apply(hosts(&["half-2.example"]), MODE_APPEND);
    // 宿主在第 N 批失败 ⇒ 不提交。判定仍读上一份完整名单（keeper）。
    assert!(denylist.host_denied("keeper.example"));
    assert!(!denylist.host_denied("half-1.example"));

    // 下一次推送从头开始：旧暂存被丢弃，不会与新一批混成一份谁都没见过的名单
    denylist.apply(hosts(&["fresh.example"]), MODE_BEGIN);
    denylist.apply(hosts(&[]), MODE_COMMIT);
    assert!(denylist.host_denied("fresh.example"));
    assert!(
        !denylist.host_denied("half-2.example"),
        "被丢弃的上一轮暂存不得漏进本次提交"
    );
    assert!(
        !denylist.host_denied("keeper.example"),
        "提交是整体换，不是并集"
    );
}

/// **无会话时提交必须什么都不换**——不得凭空把活动快照清成空名单。
///（反过来，"会话存在就提交"落地的就是那一份可能残缺的暂存：
/// 「只在整链成功时 commit」是宿主侧义务，由 C# 的分批提交测试钉住。）
#[test]
fn commit_without_a_session_changes_nothing() {
    let fresh = HostDenylist::default();
    fresh.apply(hosts(&["keeper.example"]), MODE_REPLACE);
    let report = fresh.apply(hosts(&[]), MODE_COMMIT);
    assert_eq!(report.accepted, 0, "无会话可提交时不得声称提交了");
    assert_eq!(report.served, 1, "游离提交不得把活动快照清空");
    assert!(fresh.host_denied("keeper.example"));
}

/// 旧宿主的两个档位逐字不变：追加无会话时进活动快照；整批替换顺带关闭会话。
#[test]
fn legacy_append_and_replace_paths_stay_untouched() {
    let legacy = HostDenylist::default();
    legacy.apply(hosts(&["a.example"]), MODE_REPLACE);
    let append = legacy.apply(hosts(&["b.example"]), MODE_APPEND);
    assert!(!append.staged, "旧宿主只发 0/1 ⇒ 永远不该有会话打开");
    assert_eq!(append.served, 2, "无会话时追加直接进活动快照（既往语义）");
    assert!(legacy.host_denied("b.example"));

    let with_session = HostDenylist::default();
    with_session.apply(hosts(&["staged.example"]), MODE_BEGIN);
    let replaced = with_session.apply(hosts(&["only.example"]), MODE_REPLACE);
    assert!(!replaced.staged, "整批替换必须顺带丢弃未提交会话");
    assert!(!with_session.host_denied("staged.example"));
    assert!(with_session.host_denied("only.example"));
}

/// 未知档位什么都不改、如实报 0（静默 reinterpret 会让下一版新增档位时
/// 把旧核心的行为错认成新行为）。
#[test]
fn unknown_mode_changes_nothing_and_is_rejected() {
    assert!(mode_is_known(MODE_BEGIN) && mode_is_known(MODE_COMMIT));
    assert!(!mode_is_known(4) && !mode_is_known(-1));
    let denylist = HostDenylist::default();
    denylist.apply(hosts(&["keeper.example"]), MODE_REPLACE);
    let report = denylist.apply(hosts(&["ghost.example"]), 4);
    assert_eq!(report.accepted, 0);
    assert_eq!(report.served, 1);
    assert!(!denylist.host_denied("ghost.example"));
    assert!(denylist.host_denied("keeper.example"));
}

/// 空名单的合法提交：清空活动快照（不 deny-all 的既有前提要保持可验证）。
#[test]
fn committing_an_empty_session_empties_the_served_snapshot() {
    let denylist = HostDenylist::default();
    denylist.apply(hosts(&["evil.example"]), MODE_REPLACE);
    denylist.apply(hosts(&[]), MODE_BEGIN);
    let commit = denylist.apply(hosts(&[]), MODE_COMMIT);
    assert_eq!(commit.accepted, 1, "换了快照就是换了，哪怕换成空");
    assert_eq!(commit.served, 0);
    assert!(!denylist.host_denied("evil.example"));
}

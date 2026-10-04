use super::*;

/// 黑名单在 evaluate 之后新增 → 已签发授权在 consume 点被复判拒绝。
/// 这是 TOCTOU 收口断言：若只在 evaluate 判一次，60s 有效期内
/// 订阅源更新对已授权导航完全不生效（审计第六轮延续 2026-10-04）。
#[test]
fn blocklist_added_after_issue_is_enforced_at_consume() {
    let broker = FfiBroker::new("1.0".into());
    assert!(broker.create_session("s".into(), "t".into(), 0, 60));
    let url = "https://late-block.example/x";

    // 未注入黑名单时正常签发
    let FfiDecision::Allow { action } =
        broker.evaluate_navigation("s".into(), "t".into(), 0, url.into(), "navigation".into())
    else {
        panic!("签发前 host 不在黑名单，应放行");
    };

    // 授权到手之后订阅源刷新，新增该 host
    assert_eq!(
        broker.update_host_denylist(vec!["late-block.example".into()]),
        1,
        "黑名单条目形态合法应被接受"
    );

    // 消费点必须复判拒绝，而不是沿用签发时刻的判定
    match broker.consume_navigation(action, url.into(), "navigation".into()) {
        FfiDecision::Deny { reason } => assert_eq!(
            reason.code, "threat_blocklist",
            "consume 复判应给出 threat_blocklist，实际 {}",
            reason.code
        ),
        other => panic!("黑名单新增后 consume 不得放行，实际 {other:?}"),
    }
}

/// 复判与 evaluate **同源**的父域证明（第七轮 R7-RS-01）：条目登记为父域
/// `late-parent.example`，签发时 host 是其子域且尚未拉黑，注入后 consume 必须
/// 沿同一条后缀链拒绝。若 consume 侧另写一份 `contains(host)` 精确匹配，本用例
/// 即红——向量抓不到这条（evaluate 先拒，consume 分支根本不可达）。
#[test]
fn blocklist_parent_domain_entry_is_enforced_at_consume_by_suffix_chain() {
    let broker = FfiBroker::new("1.0".into());
    assert!(broker.create_session("s".into(), "t".into(), 0, 60));
    let url = "https://cdn.late-parent.example/x";
    let FfiDecision::Allow { action } =
        broker.evaluate_navigation("s".into(), "t".into(), 0, url.into(), "navigation".into())
    else {
        panic!("注入前子域不在黑名单，应放行");
    };

    // 授权到手之后订阅源刷新，新增**父域**条目（精确匹配永远命中不了子域）
    assert_eq!(
        broker.update_host_denylist(vec!["late-parent.example".into()]),
        1,
        "父域条目形态合法应被接受"
    );

    match broker.consume_navigation(action, url.into(), "navigation".into()) {
        FfiDecision::Deny { reason } => assert_eq!(
            reason.code, "threat_blocklist",
            "consume 复判应走同一条后缀链，实际 {}",
            reason.code
        ),
        other => panic!("父域新增后 consume 不得放行子域，实际 {other:?}"),
    }
}

/// 反向对照：同一 host 未被拉黑时，consume 仍正常放行——
/// 防止复判实现退化为恒拒（恒拒同样是假闭环）。
#[test]
fn unblocklisted_host_still_consumes() {
    let broker = FfiBroker::new("1.0".into());
    assert!(broker.create_session("s".into(), "t".into(), 0, 60));
    let url = "https://fine.example/x";
    let FfiDecision::Allow { action } =
        broker.evaluate_navigation("s".into(), "t".into(), 0, url.into(), "navigation".into())
    else {
        panic!("应放行");
    };
    broker.update_host_denylist(vec!["other.example".into()]);
    assert!(
        matches!(
            broker.consume_navigation(action, url.into(), "navigation".into()),
            FfiDecision::Allow { .. }
        ),
        "未命中黑名单的既有授权必须仍可消费"
    );
}

/// 高危目标经批准后仍可消费（复判只针对黑名单，不针对高危）——
/// 否则用户刚批准的本机导航会被自己否决，确认流成死路径。
#[test]
fn approved_loopback_navigation_can_consume() {
    let broker = FfiBroker::new("1.0".into());
    assert!(broker.create_session("s".into(), "t".into(), 0, 60));
    let url = "https://127.0.0.1:8080/admin";
    let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
        "s".into(),
        "t".into(),
        0,
        url.into(),
        "navigation".into(),
    ) else {
        panic!("本机目标应走待审批");
    };
    let FfiDecision::Allow { action } =
        broker.approve_navigation_confirmation(request.nonce, url.into(), "navigation".into())
    else {
        panic!("批准应发放授权");
    };
    assert!(
        matches!(
            broker.consume_navigation(action, url.into(), "navigation".into()),
            FfiDecision::Allow { .. }
        ),
        "批准后的本机导航应可消费——高危复判会摧毁确认流"
    );
}

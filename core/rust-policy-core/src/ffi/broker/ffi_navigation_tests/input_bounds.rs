// R9-B63：宿主直传输入的**存**侧口径——policy_version 与会话键。
//
// 这一族的既有覆盖面（`url_limits.rs` / `decision_details.rs`）判的是 URL 与 scope。
// 本文件补另外两条：构造期版本串会被 clone 进每条签发的授权（账本上限 50K ⇒
// 一份输入换成 50K 份驻留），会话键超长则会在「查不到」那条 deny 文案里被原样
// 回显两遍。两条都判**可观察面**：载荷里实际生效的版本串、deny 文案的长度与内容、
// 以及两个账本有没有被碰。
//
// 反向对照写在这里而不是只写在门禁里：门禁（scripts/verify_ffi_input_bounds.py 判据
// 5/6）按文本判「排在分配之前」，本文件按返回值判「拒了之后状态与文案长什么样」。

use super::super::*;

use super::common::*;

/// 取一条 Allow 载荷（失败即 panic，附带实际决策）。
fn allow_of(decision: FfiDecision) -> FfiAuthorizedAction {
    match decision {
        FfiDecision::Allow { action } => action,
        other => panic!("容量内必须放行，实际 {other:?}"),
    }
}

#[test]
fn oversized_policy_version_stays_out_of_both_the_payload_and_the_ledger() {
    let long = "v".repeat(input_bounds::MAX_POLICY_VERSION_BYTES + 1);
    let broker = FfiBroker::new(long.clone());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    let action = allow_of(broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/a".into(),
        "navigation".into(),
    ));
    // 宿主可见面：回显的是**实际生效**的版本，不是静默截断的长串——退回可观察
    assert_eq!(action.policy_version, DEFAULT_POLICY_VERSION);
    // 内存面：账本里驻留的那条同样有界（这才是 50K × 输入长度那条放大面）
    let ledger = broker.issued_actions.lock().expect("账本锁");
    let stored = match ledger.values().next().expect("Allow 必留下一条账本记录") {
        IssuedAuthorization::Pending(action) => action,
        other => panic!("首次签发应是 Pending，实际 {other:?}"),
    };
    assert_eq!(stored.policy_version, DEFAULT_POLICY_VERSION);
}

#[test]
fn policy_version_at_the_cap_is_kept_verbatim() {
    // 边界内侧：恰上限的版本串原样保留——证明上一条拒的是长度而不是「一律丢弃」
    let at_cap = "w".repeat(input_bounds::MAX_POLICY_VERSION_BYTES);
    let broker = FfiBroker::new(at_cap.clone());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    assert_eq!(
        allow_of(broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        ))
        .policy_version,
        at_cap
    );
}

#[test]
fn oversized_session_key_is_denied_without_echo_or_state_change() {
    let cap = MAX_SESSION_KEY_BYTES;
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    // 另一侧用带连字符的短哨兵：回声断言只对**超长那一个**字段有意义——
    // 拿 "t" 去断言「文案里没有它」必假（"tab" 这个词里就有个 t），这条用例
    // 初版就是这么红的。
    for (session, tab) in [
        ("s".repeat(cap + 1), "tab-ok".to_string()),
        ("session-ok".to_string(), "t".repeat(cap + 1)),
    ] {
        let oversized = if session.len() > cap { &session } else { &tab };
        let decision = broker.evaluate_navigation(
            session.clone(),
            tab.clone(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        let FfiDecision::Deny { reason } = decision else {
            panic!(
                "超长会话键（{} 字节）必须先拒，实际 {decision:?}",
                oversized.len()
            );
        };
        assert_eq!(reason.code, "ffi_session_key_too_long");
        // 回声面：文案只放长度数字，不放宿主原串。旧形态走 core 的
        // session_not_found，把整个 257 字节的键原样写进 detail 与 explanation
        // 各一遍——拆掉入口护栏后这两条断言实测都抓到了它。
        for text in [&reason.detail, &reason.explanation] {
            assert!(
                !text.contains(oversized.as_str()),
                "deny 文案回显了宿主原串：{text}"
            );
            // 拒绝一个 N 字节的输入，不该回一条不比它短的文案——放大即缺陷
            assert!(
                text.len() < oversized.len(),
                "deny 文案不瘦于输入：{}",
                text.len()
            );
        }
        // 状态面：两个账本都没被这条输入碰到
        assert!(broker.issued_actions.lock().expect("账本锁").is_empty());
        assert!(broker
            .pending_navigation_approvals
            .lock()
            .expect("待审批锁")
            .is_empty());
    }
}

#[test]
fn session_key_at_the_cap_still_navigates() {
    // 会话键的边界内侧（create_session 与 evaluate 同口径 ⇒ 合法键不会被入口误拒）
    let key = "k".repeat(MAX_SESSION_KEY_BYTES);
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session(key.clone(), "t".into(), 1, 60));
    assert!(matches!(
        broker.evaluate_navigation(
            key,
            "t".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        ),
        FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
    ));
}

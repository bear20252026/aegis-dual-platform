use super::super::*;

use super::common::*;

// —— RS-135（审计 2026-09-25）：容量/清理/覆盖语义 ——

#[test]
fn destroy_session_clears_issued_and_pending_ledgers() {
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
    let FfiDecision::Allow { action } = broker.evaluate_navigation(
        "s1".into(),
        "t1".into(),
        0,
        "https://example.com/a".into(),
        "navigation".into(),
    ) else {
        panic!("expected allow");
    };
    let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
        "s1".into(),
        "t1".into(),
        0,
        "https://169.254.169.254/b".into(),
        "navigation".into(),
    ) else {
        panic!("expected pending");
    };
    assert!(broker.destroy_session("s1".into()));
    // 已签发授权随销毁清理（不退化为 nonce_replay——是撤销）
    match broker.consume_navigation(action, "https://example.com/a".into(), "navigation".into()) {
        FfiDecision::Deny { reason } => {
            assert_ne!(reason.code, "nonce_replay", "销毁清理 ≠ 已消费重放");
        }
        _ => panic!("destroyed session must not consume"),
    }
    // 待审批请求随销毁清理
    match broker.approve_navigation_confirmation(
        request.nonce,
        "https://169.254.169.254/b".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_not_pending"),
        _ => panic!("pending approval must be revoked on session destroy"),
    }
}

#[test]
fn reject_and_empty_nonce_are_fail_closed() {
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
    // 未知 nonce / 空 nonce / 已拒绝后的二次拒绝——一律 false
    assert!(!broker.reject_navigation_confirmation("no-such".into()));
    assert!(!broker.reject_navigation_confirmation(String::new()));
    let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
        "s1".into(),
        "t1".into(),
        0,
        "https://169.254.169.254/c".into(),
        "navigation".into(),
    ) else {
        panic!("expected pending");
    };
    assert!(broker.reject_navigation_confirmation(request.nonce.clone()));
    assert!(
        !broker.reject_navigation_confirmation(request.nonce),
        "二次拒绝 false"
    );
    // 空 nonce 的审批入口同样 fail-closed
    match broker.approve_navigation_confirmation(
        String::new(),
        "https://169.254.169.254/c".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_not_pending"),
        _ => panic!("empty nonce must not approve"),
    }
}

#[test]
fn pending_approval_capacity_is_fail_closed() {
    // MAX_PENDING_APPROVALS=1024：填满后第 1025 个请求 fail-closed
    // 拒绝（此前无上限可堆叠内存 DoS）；全部未过期，惰性清理不腾位
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
    for i in 0..MAX_PENDING_APPROVALS {
        let url = format!("https://169.254.169.254/pending/{i}");
        let decision = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            url.clone(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::RequireConfirmation { .. }),
            "第 {i} 个待审批请求必须登记成功"
        );
    }
    let overflow = broker.request_navigation_confirmation(
        "s1".into(),
        "t1".into(),
        0,
        "https://169.254.169.254/overflow".into(),
        "navigation".into(),
    );
    match overflow {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_ledger"),
        FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. } => {
            panic!("capacity overflow must deny")
        }
    }
}

#[test]
fn create_session_same_id_replaces_prior_generation() {
    // RS-033 契约在 FFI 层的镜像：同 id create_session = 显式 replace——
    // 旧代际授权/验证立即失效，新代际生效
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s1".into(), "t1".into(), 1, 60));
    assert!(broker.create_session("s1".into(), "t1".into(), 2, 60));
    assert!(
        matches!(
            broker.evaluate_navigation(
                "s1".into(),
                "t1".into(),
                1,
                "https://example.com/".into(),
                "navigation".into(),
            ),
            FfiDecision::Deny { .. }
        ),
        "replace 后旧代际必须失效"
    );
    assert!(matches!(
        broker.evaluate_navigation(
            "s1".into(),
            "t1".into(),
            2,
            "https://example.com/".into(),
            "navigation".into(),
        ),
        FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
    ));
}

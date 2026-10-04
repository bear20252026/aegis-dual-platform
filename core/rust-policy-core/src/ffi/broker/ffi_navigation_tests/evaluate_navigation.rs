use super::super::*;

use super::common::*;

#[test]
fn evaluate_navigation_denies_unknown_session() {
    let broker = FfiBroker::new(POLICY_VERSION.into());
    let decision = broker.evaluate_navigation(
        "no-such-session".into(),
        "tab-1".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    );
    assert!(
        matches!(decision, FfiDecision::Deny { .. }),
        "未知会话必须拒绝（fail-closed）"
    );
}

#[test]
fn evaluate_navigation_allows_valid_session() {
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s1".into(), "tab-1".into(), 1, 60));
    let decision = broker.evaluate_navigation(
        "s1".into(),
        "tab-1".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    );
    assert!(
        matches!(
            decision,
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
        ),
        "有效会话 + 可解析 https URL 应放行或要求确认"
    );
}

#[test]
fn evaluate_navigation_denies_unparseable_url() {
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s2".into(), "tab-1".into(), 1, 60));
    let decision = broker.evaluate_navigation(
        "s2".into(),
        "tab-1".into(),
        1,
        "file:///etc/passwd".into(),
        "navigation".into(),
    );
    assert!(
        matches!(decision, FfiDecision::Deny { .. }),
        "file:// 非 http(s) scheme 必须在 URL 解析层拒绝"
    );
}

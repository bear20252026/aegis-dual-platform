use super::super::*;

use super::common::*;

#[test]
fn url_entries_reject_oversized_raw_url_before_parsing() {
    // RS-282：evaluate/approve/consume 的 raw_url 此前无前置上限（URL
    // 三入口有 MAX_FFI_URL_BYTES，这三处直通深解析）——超长先拒
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    let oversized = format!("https://example.com/{}", "a".repeat(70 * 1024));
    match broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        oversized.clone(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_url_too_long"),
        other => panic!("evaluate 超长 raw_url 必须先拒，实际 {other:?}"),
    }
    // approve：超长先于 pending 移除（nonce 状态不被超长输入改变）
    let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
        "s".into(),
        "t".into(),
        1,
        "https://169.254.169.254/ok".into(),
        "navigation".into(),
    ) else {
        panic!("正常请求必须登记")
    };
    match broker.approve_navigation_confirmation(
        request.nonce.clone(),
        oversized.clone(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_url_too_long"),
        other => panic!("approve 超长 raw_url 必须先拒，实际 {other:?}"),
    }
    // pending 记录未被消费——正常 URL 仍可批准（先拒不改状态）
    assert!(matches!(
        broker.approve_navigation_confirmation(
            request.nonce,
            "https://169.254.169.254/ok".into(),
            "navigation".into()
        ),
        FfiDecision::Allow { .. }
    ));
    // consume：超长同样先拒
    let FfiDecision::Allow { action } = broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/once".into(),
        "navigation".into(),
    ) else {
        panic!("容量内必须放行")
    };
    match broker.consume_navigation(action, oversized, "navigation".into()) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_url_too_long"),
        other => panic!("consume 超长 raw_url 必须先拒，实际 {other:?}"),
    }
}

#[test]
fn redact_url_truncates_oversized_host_segment() {
    // RS-282：redact 的 host 段截断（256B）——deny 文案内嵌 host 由
    // URL 攻击者可控，脱敏输出必须有界
    let long_host = "a".repeat(300);
    let url = format!("https://{long_host}/p");
    let redacted = redact_url_for_log(&url);
    assert!(
        redacted.len() <= "https://".len() + MAX_REDACT_HOST_BYTES,
        "host 段截断到 256B：{}",
        redacted.len()
    );
    // 正常长度 host 不受影响（既有锚点回归）
    assert_eq!(
        redact_url_for_log("https://example.com/p?token=1#f"),
        "https://example.com"
    );
}

#[test]
fn destroy_session_distinguishes_missing_id() {
    // RS-286：destroy 对不存在的 id 此前恒 true——core 层改返回 bool
    // 后宿主可区分「已销毁」与「本来就不存在」
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    assert!(broker.destroy_session("s".into()), "存在 id 销毁 true");
    assert!(
        !broker.destroy_session("s".into()),
        "二次销毁（已不存在）false"
    );
    assert!(!broker.destroy_session("never".into()), "不存在 id false");
}

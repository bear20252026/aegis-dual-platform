use super::super::*;

use super::common::*;

// —— RS-253/254/258/270 回归（审计 2026-10-01） ——

#[test]
fn empty_policy_version_defaults_on_uniffi_path() {
    // RS-253：C ABI 拒空 policy_version（aegis_policy_core_broker_new 返回
    // null）；UniFFI constructor 不可失败——空版本按「默认版本」收口：
    // 签发的 action 携带哨兵版本，与 broker 自身校验自洽
    let broker = FfiBroker::new(String::new());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    let decision = broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    );
    match decision {
        FfiDecision::Allow { action } => {
            assert_eq!(action.policy_version, DEFAULT_POLICY_VERSION);
        }
        other => panic!("空版本默认化后导航应正常评估，实际 {other:?}"),
    }
    // C ABI 侧仍拒绝空版本（行为差异以测试锚点双端登记）
    // —— 见 c_abi::tests::c_abi_rejects_empty_policy_version
}

#[test]
fn evaluate_navigation_rejects_oversized_scope() {
    // RS-254：scope 长度上限 256（与 RS-223 会话键同口径）——
    // 此前 FFI 边界对 scope 无长度防线
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    let oversized = "x".repeat(MAX_SCOPE_BYTES + 1);
    match broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/".into(),
        oversized,
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_scope_too_long"),
        other => panic!("超长 scope 必须拒绝，实际 {other:?}"),
    }
    // 恰 256 字节放行（边界内侧）
    let at_cap = "y".repeat(MAX_SCOPE_BYTES);
    assert!(matches!(
        broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/".into(),
            at_cap,
        ),
        FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
    ));
}

#[test]
fn deny_reasons_redact_url_query_and_userinfo() {
    // RS-258：url_policy deny 的 detail/explanation 不得内嵌完整明文
    // URL——query（token 载体）与 userinfo 剥除（AD-211 的 Rust 同步）
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    // 对照锚点：可解析 URL 正常评估（token 在 query 中但页面可解析，
    // 非 deny 路径——不进入文案面）
    let token_url = "https://example.com/path?session_token=SECRET&x=1#frag";
    assert!(matches!(
        broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            token_url.into(),
            "navigation".into(),
        ),
        FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
    ));
    // 解析失败路径：userinfo 形态被 canonicalize 拒绝
    // （canonicalize_external 拒 userinfo），deny 文案应只含 host
    let userinfo_url = "https://user:secretpw@example.com/path?token=LEAK";
    let denied = match broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        userinfo_url.into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => reason,
        other => panic!("userinfo URL 应被拒，实际 {other:?}"),
    };
    let combined = format!("{}{}", denied.detail, denied.explanation);
    assert!(
        !combined.contains("secretpw") && !combined.contains("LEAK"),
        "凭据/query token 不得泄入 deny 文案：{combined}"
    );
    assert!(
        combined.contains("example.com"),
        "host 可保留（定位信息）：{combined}"
    );
    // 脱敏单源函数直测：query/fragment/userinfo 全剥、scheme+host 保留
    assert_eq!(
        redact_url_for_log("https://example.com/p?token=1#f"),
        "https://example.com"
    );
    assert_eq!(
        redact_url_for_log("https://u:p@example.com:8443/p"),
        "https://example.com:8443"
    );
    assert_eq!(redact_url_for_log("not a url"), "<opaque-url>");
}

#[test]
fn zero_expiry_window_issues_immediately_expired_actions() {
    // RS-270：ACTION_EXPIRY_SECONDS 可测参数化——注入 0 秒窗口后签发的
    // 授权 expires_at == 签发时刻，evaluate 自身的会话验证即判过期
    // （RS-156 口径 == now 即过期），参数真实生效
    let broker = FfiBroker::with_action_expiry(POLICY_VERSION.into(), TEST_ACTION_EXPIRY_SECONDS);
    assert!(broker.create_session("s".into(), "t".into(), 1, 120));
    match broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "action_expired"),
        other => panic!("零窗口签发必须即刻过期，实际 {other:?}"),
    }
}

#[test]
fn expired_pending_approval_and_issued_action_rejected() {
    // RS-270：过期 approve/consume 分支直测——向两本账本注入已过期授权
    // （expires_at < now，确定性构造，无时钟竞态），绑定全部匹配的
    // 前提下必须以 action_expired 拒绝（此前恒 120s 窗口零覆盖）
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 120));
    let now = crate::broker::now_unix_secs().unwrap_or(0);
    let expired = AuthorizedAction {
        session_id: "s".into(),
        tab_id: "t".into(),
        document_generation: 1,
        origin: "https://example.com".into(),
        method: "GET".into(),
        canonical_parameters: "/late".into(),
        scope: "navigation".into(),
        expires_at: now.saturating_sub(1),
        nonce: "expired-nonce".into(),
        policy_version: POLICY_VERSION.into(),
        explanation: String::new(),
    };
    // approve 侧：pending 账本中的过期授权 → action_expired
    broker
        .pending_navigation_approvals
        .lock()
        .unwrap()
        .insert("expired-nonce".into(), expired.clone());
    match broker.approve_navigation_confirmation(
        "expired-nonce".into(),
        "https://example.com/late".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "action_expired"),
        other => panic!("过期授权 approve 必须拒绝，实际 {other:?}"),
    }
    // consume 侧：issued 账本中的过期 Pending 授权 → action_expired
    broker.issued_actions.lock().unwrap().insert(
        "expired-nonce".into(),
        IssuedAuthorization::Pending(Box::new(expired)),
    );
    match broker.consume_navigation(
        FfiAuthorizedAction {
            session_id: "s".into(),
            tab_id: "t".into(),
            document_generation: 1,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/late".into(),
            scope: "navigation".into(),
            expires_at: now.saturating_sub(1),
            nonce: "expired-nonce".into(),
            policy_version: POLICY_VERSION.into(),
            explanation: String::new(),
        },
        "https://example.com/late".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "action_expired"),
        other => panic!("过期授权 consume 必须拒绝，实际 {other:?}"),
    }
}

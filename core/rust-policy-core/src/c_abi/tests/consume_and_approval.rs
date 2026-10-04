use super::super::*;

use super::common::*;

#[test]
fn c_abi_evaluates_and_consumes_navigation_once() {
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let session = c_string("session-1");
    let tab = c_string("tab-1");
    assert_eq!(
        aegis_policy_core_broker_create_session(broker, session.as_ptr(), tab.as_ptr(), 0, 60),
        1
    );
    let url = c_string("HTTPS://Example.COM:443/path?query=1#ignored");
    let scope = c_string("navigation");
    let decision = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        session.as_ptr(),
        tab.as_ptr(),
        0,
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(decision["decision"], "allow");
    assert_eq!(decision["action"]["origin"], "https://example.com");
    assert_eq!(decision["action"]["canonical_parameters"], "/path?query=1");
    let action = c_string(&decision["action"].to_string());
    let first = read_response(aegis_policy_core_broker_consume_navigation_json(
        broker,
        action.as_ptr(),
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(first["decision"], "allow");
    let replay = read_response(aegis_policy_core_broker_consume_navigation_json(
        broker,
        action.as_ptr(),
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(replay["decision"], "deny");
    assert_eq!(replay["reason"]["code"], "nonce_replay");
    // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
    unsafe { aegis_policy_core_broker_free(broker) };
}

/// 回归防护（C# 往返缺陷）：托管端 NativeAction 序列化不携带 explanation，
/// consume 绑定比较必须忽略该审计字段——否则合法一次消费被误判
/// action_not_issued（安装版崩溃排查中暴露的确定性缺陷）。
#[test]
fn c_abi_consume_accepts_action_without_explanation_field() {
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let session = c_string("session-1");
    let tab = c_string("tab-1");
    assert_eq!(
        aegis_policy_core_broker_create_session(broker, session.as_ptr(), tab.as_ptr(), 0, 60),
        1
    );
    let url = c_string("https://example.com/path?query=1");
    let scope = c_string("navigation");
    let decision = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        session.as_ptr(),
        tab.as_ptr(),
        0,
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(decision["decision"], "allow");
    // 模拟 C# NativeAction 往返：从评估响应剥离 explanation 审计字段。
    let mut action_obj = decision["action"].clone();
    assert!(action_obj
        .as_object_mut()
        .unwrap()
        .remove("explanation")
        .is_some());
    let action = c_string(&action_obj.to_string());
    let first = read_response(aegis_policy_core_broker_consume_navigation_json(
        broker,
        action.as_ptr(),
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(
        first["decision"], "allow",
        "省略 explanation 的 action 仍应可被消费（绑定比较忽略审计字段）"
    );
    // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
    unsafe { aegis_policy_core_broker_free(broker) };
}

#[test]
fn c_abi_requires_explicit_approval_before_issuing_navigation_action() {
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    let session = c_string("confirmation-session");
    let tab = c_string("confirmation-tab");
    let url = c_string("https://127.0.0.1/confirm?transfer=1");
    let mismatched_url = c_string("https://127.0.0.1/confirm?transfer=2");
    let scope = c_string("navigation");
    assert_eq!(
        aegis_policy_core_broker_create_session(broker, session.as_ptr(), tab.as_ptr(), 0, 60),
        1
    );
    let pending = read_response(
        aegis_policy_core_broker_request_navigation_confirmation_json(
            broker,
            session.as_ptr(),
            tab.as_ptr(),
            0,
            url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    assert_eq!(pending["decision"], "require_confirmation");
    let nonce = c_string(
        pending["request"]["nonce"]
            .as_str()
            .expect("approval nonce"),
    );

    let mismatch = read_response(
        aegis_policy_core_broker_approve_navigation_confirmation_json(
            broker,
            nonce.as_ptr(),
            mismatched_url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    assert_eq!(mismatch["decision"], "deny");
    assert_eq!(mismatch["reason"]["code"], "approval_binding_mismatch");
    let unavailable = read_response(
        aegis_policy_core_broker_approve_navigation_confirmation_json(
            broker,
            nonce.as_ptr(),
            url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    assert_eq!(unavailable["reason"]["code"], "approval_not_pending");

    let pending = read_response(
        aegis_policy_core_broker_request_navigation_confirmation_json(
            broker,
            session.as_ptr(),
            tab.as_ptr(),
            0,
            url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    let nonce = c_string(
        pending["request"]["nonce"]
            .as_str()
            .expect("approval nonce"),
    );
    let approved = read_response(
        aegis_policy_core_broker_approve_navigation_confirmation_json(
            broker,
            nonce.as_ptr(),
            url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    assert_eq!(approved["decision"], "allow");
    let action = c_string(&approved["action"].to_string());
    let consumed = read_response(aegis_policy_core_broker_consume_navigation_json(
        broker,
        action.as_ptr(),
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(consumed["decision"], "allow");

    let pending = read_response(
        aegis_policy_core_broker_request_navigation_confirmation_json(
            broker,
            session.as_ptr(),
            tab.as_ptr(),
            0,
            url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    let rejected_nonce = c_string(
        pending["request"]["nonce"]
            .as_str()
            .expect("approval nonce"),
    );
    assert_eq!(
        aegis_policy_core_broker_reject_navigation_confirmation(broker, rejected_nonce.as_ptr()),
        1
    );
    let rejected = read_response(
        aegis_policy_core_broker_approve_navigation_confirmation_json(
            broker,
            rejected_nonce.as_ptr(),
            url.as_ptr(),
            scope.as_ptr(),
        ),
    );
    assert_eq!(rejected["reason"]["code"], "approval_not_pending");
    // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
    unsafe { aegis_policy_core_broker_free(broker) };
}

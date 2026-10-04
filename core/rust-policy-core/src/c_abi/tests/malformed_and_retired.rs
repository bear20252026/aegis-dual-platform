use super::super::*;

use super::common::*;

// ===== RS-138（审计 2026-09-25）：畸形 JSON / null 指针 / retired =====

#[test]
fn consume_with_malformed_action_json_is_typed_deny() {
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let not_json = c_string("{not json");
    let url = c_string("https://127.0.0.1/");
    let scope = c_string("navigation");
    let res = read_response(aegis_policy_core_broker_consume_navigation_json(
        broker,
        not_json.as_ptr(),
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(res["decision"], "deny");
    assert_eq!(res["reason"]["code"], "ffi_action_invalid_json");
    // 结构合法但字段缺失/为空 → ffi_action_invalid
    let missing = c_string(r#"{"session_id":"s"}"#);
    let res2 = read_response(aegis_policy_core_broker_consume_navigation_json(
        broker,
        missing.as_ptr(),
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(res2["reason"]["code"], "ffi_action_invalid");
    // SAFETY: broker 由本测试创建。
    unsafe { aegis_policy_core_broker_free(broker) };
}

#[test]
fn null_input_pointers_surface_typed_error_codes() {
    // RS-141 联动：read_utf8 细分错误码必须透传（此前折叠为
    // ffi_input_invalid）
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let session = c_string("s");
    let tab = c_string("t");
    let url = c_string("https://127.0.0.1/");
    let scope = c_string("navigation");
    // null session 指针 → ffi_input_null（非折叠码）
    let res = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        ptr::null(),
        tab.as_ptr(),
        0,
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(res["reason"]["code"], "ffi_input_null");
    // null URL 指针 → ffi_input_null
    let res2 = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        session.as_ptr(),
        tab.as_ptr(),
        0,
        ptr::null(),
        scope.as_ptr(),
    ));
    assert_eq!(res2["reason"]["code"], "ffi_input_null");
    // SAFETY: broker 由本测试创建。
    unsafe { aegis_policy_core_broker_free(broker) };
}

#[test]
fn retired_broker_rejects_u8_entry_points() {
    // retired 后 create/reject 入口返回 0（JSON 入口已由
    // freed_broker_retires_cleanly_without_ub 锁定）
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let sid = c_string("s");
    let tid = c_string("t");
    let nonce = c_string("n");
    // SAFETY: broker 由本测试创建。
    unsafe { aegis_policy_core_broker_free(broker) };
    assert_eq!(
        aegis_policy_core_broker_create_session(broker, sid.as_ptr(), tid.as_ptr(), 0, 60),
        0
    );
    assert_eq!(
        aegis_policy_core_broker_reject_navigation_confirmation(broker, nonce.as_ptr()),
        0
    );
}

#[test]
fn extreme_generation_and_ttl_do_not_panic() {
    // u64::MAX generation / u64::MAX ttl 组合：无 panic，语义 fail-closed
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let sid = c_string("s-max");
    let tid = c_string("t");
    let url = c_string("https://127.0.0.1/");
    let scope = c_string("navigation");
    assert_eq!(
        aegis_policy_core_broker_create_session(
            broker,
            sid.as_ptr(),
            tid.as_ptr(),
            u64::MAX,
            u64::MAX,
        ),
        1
    );
    // 代际 u64::MAX 匹配 → 可放行；再推进一步必然失败（无更大代际）
    let res = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        sid.as_ptr(),
        tid.as_ptr(),
        u64::MAX,
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert!(res["decision"] == "allow" || res["decision"] == "require_confirmation");
    assert_eq!(
        aegis_policy_core_broker_advance_document_generation(broker, sid.as_ptr(), tid.as_ptr(), 0),
        0,
        "代际回退必须拒绝"
    );
    // SAFETY: broker 由本测试创建。
    unsafe { aegis_policy_core_broker_free(broker) };
}

#[test]
fn fallback_response_prebuilt_is_valid_json() {
    // RS-139：预构造 FALLBACK——无 panic 路径且字节是合法 deny JSON
    let text = FALLBACK_RESPONSE.to_str().expect("ASCII");
    let parsed: serde_json::Value = serde_json::from_str(text).expect("FALLBACK 必须是合法 JSON");
    assert_eq!(parsed["abi_version"], 0);
    assert_eq!(parsed["decision"], "deny");
    assert_eq!(parsed["reason"]["code"], "ffi_response_alloc");
}

#[test]
fn broker_new_enforces_single_live_instance() {
    // RS-140：活跃单例存在时二次创建返回 null（防泄漏放大）；
    // 退休后允许重建。RS-236 口径：退休分配不回收，多轮生命周期
    // 循环下线性累积（单轮 = 单份遗留）；单例互斥约束的是「同一
    // 时刻至多一份活跃」，非全进程总量
    let _serial = broker_test_guard();
    let v1 = c_string("1.0");
    let b1 = aegis_policy_core_broker_new(v1.as_ptr());
    assert!(!b1.is_null());
    let v2 = c_string("2.0");
    assert!(
        aegis_policy_core_broker_new(v2.as_ptr()).is_null(),
        "活跃单例存在时必须拒绝二次创建"
    );
    // SAFETY: b1 由本测试创建。
    unsafe { aegis_policy_core_broker_free(b1) };
    let b2 = aegis_policy_core_broker_new(v2.as_ptr());
    assert!(!b2.is_null(), "退休后允许创建新单例");
    // SAFETY: b2 由本测试创建。
    unsafe { aegis_policy_core_broker_free(b2) };
}

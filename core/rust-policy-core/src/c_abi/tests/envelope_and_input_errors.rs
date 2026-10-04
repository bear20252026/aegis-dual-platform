use super::super::*;

use super::common::*;

#[test]
fn c_abi_rejects_invalid_input_and_null_broker() {
    let _serial = broker_test_guard();
    let session = c_string("session-1");
    let tab = c_string("tab-1");
    let url = c_string("javascript:alert(1)");
    let scope = c_string("navigation");
    let null_broker = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        ptr::null_mut(),
        session.as_ptr(),
        tab.as_ptr(),
        0,
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(null_broker["reason"]["code"], "ffi_broker_null");

    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    let invalid_url = read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        session.as_ptr(),
        tab.as_ptr(),
        0,
        url.as_ptr(),
        scope.as_ptr(),
    ));
    assert_eq!(invalid_url["reason"]["code"], "url_policy");
    // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
    unsafe { aegis_policy_core_broker_free(broker) };
}

#[test]
fn c_abi_rejects_empty_policy_version() {
    let empty = c_string("");
    assert!(aegis_policy_core_broker_new(empty.as_ptr()).is_null());
}

#[test]
fn c_abi_encodes_complete_confirmation_request() {
    // RS-268：decision_json 现返回强类型 Serialize 结构——经 to_value
    // 观测 JSON 形态（与旧 Value 构造逐字段一致）
    let decision_src = FfiDecision::RequireConfirmation {
        request: FfiApprovalRequest {
            origin: "https://payments.example".into(),
            method: "POST".into(),
            path: "/transfers".into(),
            scope: "payment:create".into(),
            expires_at: 1_700_000_000,
            nonce: "approval-nonce".into(),
        },
    };
    let decision =
        serde_json::to_value(decision_json(&decision_src)).expect("typed envelope serializes");

    assert_eq!(decision["decision"], "require_confirmation");
    assert_eq!(decision["abi_version"], POLICY_CORE_ABI_VERSION);
    assert_eq!(decision["request"]["origin"], "https://payments.example");
    assert_eq!(decision["request"]["method"], "POST");
    assert_eq!(decision["request"]["path"], "/transfers");
    assert_eq!(decision["request"]["scope"], "payment:create");
    assert_eq!(decision["request"]["expires_at"], 1_700_000_000);
    assert_eq!(decision["request"]["nonce"], "approval-nonce");
}

/// RS-268：强类型信封的 flatten 输出与宿主 JSON 契约逐字段一致——
/// abi_version 平铺在顶层，决策字段随 tag 展开（不出现嵌套 "body"）。
#[test]
fn typed_envelope_flattens_to_legacy_json_shape() {
    let deny_envelope = deny("probe_code", "probe detail");
    let v = serde_json::to_value(&deny_envelope).expect("deny envelope serializes");
    assert_eq!(v["abi_version"], POLICY_CORE_ABI_VERSION);
    assert_eq!(v["decision"], "deny");
    assert_eq!(v["reason"]["code"], "probe_code");
    assert!(v.get("body").is_none(), "flatten 不得产生嵌套 body 键");

    let allow_src = FfiDecision::Allow {
        action: FfiAuthorizedAction {
            session_id: "s".into(),
            tab_id: "t".into(),
            document_generation: 1,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/p".into(),
            scope: "navigation".into(),
            expires_at: 42,
            nonce: "n".into(),
            policy_version: "1.0".into(),
            explanation: "expl".into(),
        },
    };
    let v = serde_json::to_value(decision_json(&allow_src)).expect("allow envelope serializes");
    assert_eq!(v["decision"], "allow");
    assert_eq!(v["action"]["session_id"], "s");
    assert_eq!(v["action"]["document_generation"], 1);
    assert_eq!(v["action"]["expires_at"], 42);
    assert_eq!(v["action"]["explanation"], "expl");
}

/// RS-176（审计 2026-09-25）：deny explanation 同步性锁定——
/// FALLBACK_JSON 是静态字节字面量（RS-139 可证无 NUL），无法引用运行时
/// 常量 NATIVE_BOUNDARY_EXPLANATION；此处双断言：字节串直接包含常量
/// 文案 + 解析后 reason.explanation 与 deny() 产出逐字相等。任一侧
/// 单独改文案都会在此测试红灯，杜绝口径分裂。
#[test]
fn fallback_json_explanation_matches_native_boundary_constant() {
    // 字节包含断言：FALLBACK_JSON 内嵌同一文案（含 JSON 转义后的引号）。
    let bytes = std::str::from_utf8(FALLBACK_JSON).expect("fallback must be UTF-8");
    assert!(
        bytes.contains(NATIVE_BOUNDARY_EXPLANATION),
        "FALLBACK_JSON must embed NATIVE_BOUNDARY_EXPLANATION verbatim"
    );

    // 解析级断言：fallback explanation 与 deny() 运行时产出一致。
    let fallback: serde_json::Value =
        serde_json::from_str(bytes).expect("fallback must be valid JSON");
    // RS-268：deny() 现返回强类型结构——经 to_value 观测
    let deny = serde_json::to_value(deny("ffi_response_alloc", "response allocation failed"))
        .expect("deny envelope serializes");
    assert_eq!(
        fallback["reason"]["explanation"], deny["reason"]["explanation"],
        "fallback and deny() must share one explanation"
    );
    assert_eq!(
        fallback["reason"]["explanation"], NATIVE_BOUNDARY_EXPLANATION,
        "explanation must equal the single-source constant"
    );
}

/// RS-175（审计 2026-09-25）：write_response 走 to_writer 单缓冲路径的
/// 回归——正常 Value 编码后经 read_response 往返必须逐字段还原（证明
/// to_writer 产出合法 JSON 且 CString NUL 终止契约未破坏）。
#[test]
fn write_response_round_trips_value_through_single_buffer() {
    // RS-175/RS-268：write_response 泛型化后 Value 仍可直接序列化——
    // 经 read_response 往返必须逐字段还原（to_writer 产出合法 JSON 且
    // CString NUL 终止契约未破坏）；强类型结构同口径往返
    let value = serde_json::json!({
        "abi_version": POLICY_CORE_ABI_VERSION,
        "decision": "deny",
        "reason": {
            "code": "probe_code",
            "detail": "probe detail",
            "explanation": NATIVE_BOUNDARY_EXPLANATION,
        },
    });
    let parsed = read_response(write_response(value.clone()));
    assert_eq!(parsed, value);
    assert_eq!(parsed["reason"]["explanation"], NATIVE_BOUNDARY_EXPLANATION);
    // 强类型 deny 信封直写同口径往返
    let typed = read_response(write_response(deny("probe_code", "probe detail")));
    assert_eq!(typed["decision"], "deny");
    assert_eq!(typed["reason"]["explanation"], NATIVE_BOUNDARY_EXPLANATION);
}

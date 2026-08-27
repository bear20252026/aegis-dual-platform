//! 稳定、最小化的 C ABI 导航决策边界。
//!
//! 此模块只在 C ABI 中交换 UTF-8 JSON，避免将 Rust 布局、指针或生命周期暴露给
//! Windows P/Invoke 与 Android JNA。所有由本模块分配的响应字符串只能通过
//! `aegis_policy_core_string_free` 释放；未知会话、无效输入和内部错误一律返回
//! 类型化的 deny JSON，而非允许宿主改用不一致的策略路径。

use crate::ffi::{FfiAuthorizedAction, FfiBroker, FfiDecision};
use crate::POLICY_CORE_ABI_VERSION;
use serde_json::{json, Value};
use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;

pub struct CAbiBroker {
    inner: FfiBroker,
}

fn read_utf8<'a>(value: *const c_char) -> Result<&'a str, &'static str> {
    if value.is_null() {
        return Err("ffi_input_null");
    }
    // SAFETY: 调用方契约要求以 NUL 结尾的有效指针；空指针在上方已拒绝。
    unsafe { CStr::from_ptr(value) }
        .to_str()
        .map_err(|_| "ffi_input_utf8")
}

fn write_response(value: Value) -> *mut c_char {
    CString::new(value.to_string())
        .map(CString::into_raw)
        .unwrap_or(ptr::null_mut())
}

fn deny(code: &str, detail: &str) -> Value {
    json!({
        "abi_version": POLICY_CORE_ABI_VERSION,
        "decision": "deny",
        "reason": {
            "code": code,
            "detail": detail,
            "explanation": "denied by aegis-policy-core native boundary"
        }
    })
}

fn action_json(action: FfiAuthorizedAction) -> Value {
    json!({
        "session_id": action.session_id,
        "tab_id": action.tab_id,
        "document_generation": action.document_generation,
        "origin": action.origin,
        "method": action.method,
        "canonical_parameters": action.canonical_parameters,
        "scope": action.scope,
        "expires_at": action.expires_at,
        "nonce": action.nonce,
        "policy_version": action.policy_version,
        "explanation": action.explanation,
    })
}

fn decision_json(decision: FfiDecision) -> Value {
    match decision {
        FfiDecision::Allow { action } => json!({
            "abi_version": POLICY_CORE_ABI_VERSION,
            "decision": "allow",
            "action": action_json(action),
        }),
        FfiDecision::RequireConfirmation { origin, method } => json!({
            "abi_version": POLICY_CORE_ABI_VERSION,
            "decision": "require_confirmation",
            "request": { "origin": origin, "method": method },
        }),
        FfiDecision::Deny { reason } => json!({
            "abi_version": POLICY_CORE_ABI_VERSION,
            "decision": "deny",
            "reason": {
                "code": reason.code,
                "detail": reason.detail,
                "explanation": reason.explanation,
            },
        }),
    }
}

fn read_string_field(value: &Value, name: &'static str) -> Result<String, &'static str> {
    value
        .get(name)
        .and_then(Value::as_str)
        .filter(|field| !field.is_empty())
        .map(ToOwned::to_owned)
        .ok_or("ffi_action_invalid")
}

fn read_u64_field(value: &Value, name: &'static str) -> Result<u64, &'static str> {
    value
        .get(name)
        .and_then(Value::as_u64)
        .ok_or("ffi_action_invalid")
}

fn parse_action(action_json: &str) -> Result<FfiAuthorizedAction, &'static str> {
    let value: Value = serde_json::from_str(action_json).map_err(|_| "ffi_action_invalid_json")?;
    Ok(FfiAuthorizedAction {
        session_id: read_string_field(&value, "session_id")?,
        tab_id: read_string_field(&value, "tab_id")?,
        document_generation: read_u64_field(&value, "document_generation")?,
        origin: read_string_field(&value, "origin")?,
        method: read_string_field(&value, "method")?,
        canonical_parameters: read_string_field(&value, "canonical_parameters")?,
        scope: read_string_field(&value, "scope")?,
        expires_at: read_u64_field(&value, "expires_at")?,
        nonce: read_string_field(&value, "nonce")?,
        policy_version: read_string_field(&value, "policy_version")?,
        explanation: value
            .get("explanation")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned(),
    })
}

fn input_deny(error: &'static str) -> *mut c_char {
    write_response(deny(error, "native policy core input rejected"))
}

fn with_broker<T>(broker: *mut CAbiBroker, operation: impl FnOnce(&CAbiBroker) -> T) -> Option<T> {
    if broker.is_null() {
        return None;
    }
    // SAFETY: 指针只能由 `aegis_policy_core_broker_new` 创建，且调用方必须在 free 前保持有效。
    Some(operation(unsafe { &*broker }))
}

/// 创建独立的原生策略 Broker；`policy_version` 为空、无效 UTF-8 或 panic 时返回 null。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_new(policy_version: *const c_char) -> *mut CAbiBroker {
    catch_unwind(AssertUnwindSafe(|| {
        let Ok(policy_version) = read_utf8(policy_version) else {
            return ptr::null_mut();
        };
        if policy_version.is_empty() {
            return ptr::null_mut();
        }
        Box::into_raw(Box::new(CAbiBroker {
            inner: FfiBroker::new(policy_version.to_owned()),
        }))
    }))
    .unwrap_or(ptr::null_mut())
}

/// 释放由 `aegis_policy_core_broker_new` 创建的 Broker；null 是幂等安全操作。
///
/// # Safety
/// `broker` 必须为本库创建、尚未释放且未被并发使用的句柄；传入任意地址或重复释放是未定义行为。
#[no_mangle]
pub unsafe extern "C" fn aegis_policy_core_broker_free(broker: *mut CAbiBroker) {
    if !broker.is_null() {
        // SAFETY: 指针所有权在此函数调用后归 Rust；调用方不得再次使用或重复释放。
        unsafe { drop(Box::from_raw(broker)) };
    }
}

/// 释放由 evaluate/consume 创建的 UTF-8 JSON 响应；null 是幂等安全操作。
///
/// # Safety
/// `response` 必须为本库 evaluate/consume 调用所返回、尚未释放的字符串指针；传入任意地址或重复释放是未定义行为。
#[no_mangle]
pub unsafe extern "C" fn aegis_policy_core_string_free(response: *mut c_char) {
    if !response.is_null() {
        // SAFETY: 仅接受由 `CString::into_raw` 返回的指针。
        unsafe { drop(CString::from_raw(response)) };
    }
}

#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_create_session(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
    tab_id: *const c_char,
    generation: u64,
    ttl_seconds: u64,
) -> u8 {
    catch_unwind(AssertUnwindSafe(|| {
        let (Ok(session_id), Ok(tab_id)) = (read_utf8(session_id), read_utf8(tab_id)) else {
            return 0;
        };
        with_broker(broker, |value| {
            value.inner.create_session(
                session_id.to_owned(),
                tab_id.to_owned(),
                generation,
                ttl_seconds,
            )
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_destroy_session(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
) -> u8 {
    catch_unwind(AssertUnwindSafe(|| {
        let Ok(session_id) = read_utf8(session_id) else {
            return 0;
        };
        with_broker(broker, |value| {
            value.inner.destroy_session(session_id.to_owned())
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_advance_document_generation(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
    tab_id: *const c_char,
    next_generation: u64,
) -> u8 {
    catch_unwind(AssertUnwindSafe(|| {
        let (Ok(session_id), Ok(tab_id)) = (read_utf8(session_id), read_utf8(tab_id)) else {
            return 0;
        };
        with_broker(broker, |value| {
            value.inner.advance_document_generation(
                session_id.to_owned(),
                tab_id.to_owned(),
                next_generation,
            )
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

/// 评估导航并返回调用方拥有的 JSON 决策；非法输入、空句柄或 panic 均返回 deny JSON。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_evaluate_navigation_json(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
    tab_id: *const c_char,
    generation: u64,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let (Ok(session_id), Ok(tab_id), Ok(raw_url), Ok(scope)) = (
            read_utf8(session_id),
            read_utf8(tab_id),
            read_utf8(raw_url),
            read_utf8(scope),
        ) else {
            return input_deny("ffi_input_invalid");
        };
        let Some(decision) = with_broker(broker, |value| {
            value.inner.evaluate_navigation(
                session_id.to_owned(),
                tab_id.to_owned(),
                generation,
                raw_url.to_owned(),
                scope.to_owned(),
            )
        }) else {
            return input_deny("ffi_broker_null");
        };
        write_response(decision_json(decision))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

/// 在副作用执行点重新校验 URL/scope，并一次性消费 action nonce。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_consume_navigation_json(
    broker: *mut CAbiBroker,
    action_json: *const c_char,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let (Ok(action_json), Ok(raw_url), Ok(scope)) =
            (read_utf8(action_json), read_utf8(raw_url), read_utf8(scope))
        else {
            return input_deny("ffi_input_invalid");
        };
        let action = match parse_action(action_json) {
            Ok(action) => action,
            Err(code) => return input_deny(code),
        };
        let Some(decision) = with_broker(broker, |value| {
            value
                .inner
                .consume_navigation(action, raw_url.to_owned(), scope.to_owned())
        }) else {
            return input_deny("ffi_broker_null");
        };
        write_response(decision_json(decision))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c_string(value: &str) -> CString {
        CString::new(value).expect("test input must not contain NUL")
    }

    fn read_response(response: *mut c_char) -> Value {
        assert!(!response.is_null());
        // SAFETY: 本测试只读取本模块返回且尚未释放的响应字符串。
        let text = unsafe { CStr::from_ptr(response) }
            .to_str()
            .expect("response must be valid UTF-8")
            .to_owned();
        // SAFETY: response 由本模块创建，且本测试仅释放一次。
        unsafe { aegis_policy_core_string_free(response) };
        serde_json::from_str(&text).expect("response must be valid JSON")
    }

    #[test]
    fn c_abi_evaluates_and_consumes_navigation_once() {
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

    #[test]
    fn c_abi_rejects_invalid_input_and_null_broker() {
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
    fn c_abi_matches_native_navigation_decision_vectors() {
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../contracts/vectors/native-navigation-decision.json"
        ))
        .expect("native navigation decision vectors must be valid JSON");

        for vector in vectors["vectors"].as_array().expect("vectors array") {
            let name = vector["name"].as_str().expect("vector name");
            let version = c_string("1.0");
            let broker = aegis_policy_core_broker_new(version.as_ptr());
            assert!(!broker.is_null(), "{name}: broker creation");
            let session = c_string("vector-session");
            let tab = c_string("vector-tab");
            let generation = vector["generation"].as_u64().expect("generation");
            if vector["register_session"].as_bool().expect("registration") {
                assert_eq!(
                    aegis_policy_core_broker_create_session(
                        broker,
                        session.as_ptr(),
                        tab.as_ptr(),
                        generation,
                        120,
                    ),
                    1,
                    "{name}: session registration"
                );
            }
            let url = c_string(vector["url"].as_str().expect("url"));
            let scope = c_string(vector["scope"].as_str().expect("scope"));
            let evaluated = read_response(aegis_policy_core_broker_evaluate_navigation_json(
                broker,
                session.as_ptr(),
                tab.as_ptr(),
                generation,
                url.as_ptr(),
                scope.as_ptr(),
            ));
            assert_eq!(
                evaluated["decision"], vector["expected_evaluate"],
                "{name}: evaluate decision"
            );
            if evaluated["decision"] == "deny" {
                assert_eq!(
                    evaluated["reason"]["code"], vector["expected_deny_code"],
                    "{name}: evaluate denial code"
                );
                // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
                unsafe { aegis_policy_core_broker_free(broker) };
                continue;
            }
            assert_eq!(
                evaluated["action"]["origin"], vector["expected_origin"],
                "{name}: canonical origin"
            );
            assert_eq!(
                evaluated["action"]["canonical_parameters"], vector["expected_parameters"],
                "{name}: canonical parameters"
            );
            let action = c_string(&evaluated["action"].to_string());
            let consume_url = c_string(vector["consume_url"].as_str().expect("consume URL"));
            let consume_scope = c_string(vector["consume_scope"].as_str().expect("consume scope"));
            let consumed = read_response(aegis_policy_core_broker_consume_navigation_json(
                broker,
                action.as_ptr(),
                consume_url.as_ptr(),
                consume_scope.as_ptr(),
            ));
            assert_eq!(
                consumed["decision"], vector["expected_consume"],
                "{name}: consume decision"
            );
            if let Some(expected_code) = vector.get("expected_consume_code") {
                assert_eq!(
                    consumed["reason"]["code"], *expected_code,
                    "{name}: consume denial"
                );
            }
            if let Some(expected_replay_code) = vector.get("expected_replay_code") {
                let replay = read_response(aegis_policy_core_broker_consume_navigation_json(
                    broker,
                    action.as_ptr(),
                    consume_url.as_ptr(),
                    consume_scope.as_ptr(),
                ));
                assert_eq!(
                    replay["reason"]["code"], *expected_replay_code,
                    "{name}: replay denial"
                );
            }
            // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
            unsafe { aegis_policy_core_broker_free(broker) };
        }
    }
}

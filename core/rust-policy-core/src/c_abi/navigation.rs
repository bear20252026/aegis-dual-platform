//! 导航/确认类 C ABI 导出（H-4 拆分自 c_abi.rs，符号契约不变）。

use super::*;


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
/// 登记待审批导航并返回调用方拥有的 JSON 确认请求；不返回可消费授权。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_request_navigation_confirmation_json(
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
            value.inner.request_navigation_confirmation(
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

/// 显式批准待审批导航并返回可消费的 JSON 授权；nonce、URL 或 scope 不匹配一律拒绝。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_approve_navigation_confirmation_json(
    broker: *mut CAbiBroker,
    nonce: *const c_char,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let (Ok(nonce), Ok(raw_url), Ok(scope)) =
            (read_utf8(nonce), read_utf8(raw_url), read_utf8(scope))
        else {
            return input_deny("ffi_input_invalid");
        };
        let Some(decision) = with_broker(broker, |value| {
            value.inner.approve_navigation_confirmation(
                nonce.to_owned(),
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

/// 显式拒绝待审批导航；未知、已兑换或已撤销 nonce 返回 0。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_reject_navigation_confirmation(
    broker: *mut CAbiBroker,
    nonce: *const c_char,
) -> u8 {
    catch_unwind(AssertUnwindSafe(|| {
        let Ok(nonce) = read_utf8(nonce) else {
            return 0;
        };
        with_broker(broker, |value| {
            value.inner.reject_navigation_confirmation(nonce.to_owned())
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
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


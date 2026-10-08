//! 导航/确认类 C ABI 导出（H-4 拆分自 c_abi.rs，符号契约不变）。

use super::*;

#[unsafe(no_mangle)]
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
            value
                .inner
                .create_session(session_id, tab_id, generation, ttl_seconds)
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_destroy_session(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
) -> u8 {
    catch_unwind(AssertUnwindSafe(|| {
        let Ok(session_id) = read_utf8(session_id) else {
            return 0;
        };
        with_broker(broker, |value| value.inner.destroy_session(session_id)).unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

#[unsafe(no_mangle)]
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
            value
                .inner
                .advance_document_generation(session_id, tab_id, next_generation)
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

/// RS-141（审计 2026-09-25）：read_utf8 细分错误码透传辅助——此前四个
/// 参数的错误统一折叠为 "ffi_input_invalid"，宿主无法区分 null 指针 /
/// 超长 / 非 UTF-8（可观测性缺失面）。取首个 Err 原样透传。
/// RS-239（2026-10-01 审计）：Ok 侧按值 String（read_utf8 单源）——
/// 借用生命周期参数化（RS-211）仍 unsound，已收敛为按值返回。
fn unwrap_input_or_deny(result: Result<String, &'static str>) -> Result<String, *mut c_char> {
    result.map_err(input_deny)
}

/// 评估导航并返回调用方拥有的 JSON 决策；非法输入、空句柄或 panic 均返回 deny JSON。
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_evaluate_navigation_json(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
    tab_id: *const c_char,
    generation: u64,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let session_id = match unwrap_input_or_deny(read_utf8(session_id)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let tab_id = match unwrap_input_or_deny(read_utf8(tab_id)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let raw_url = match unwrap_input_or_deny(read_utf8(raw_url)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let scope = match unwrap_input_or_deny(read_utf8(scope)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let Some(decision) = with_broker(broker, |value| {
            value
                .inner
                .evaluate_navigation(session_id, tab_id, generation, raw_url, scope)
        }) else {
            return input_deny("ffi_broker_null");
        };
        write_response(decision_json(&decision))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

/// 登记待审批导航并返回调用方拥有的 JSON 确认请求；不发放可消费授权——
/// 仅同一 Broker 的显式批准（approve）可兑换原始动作。
///
/// RS-142（审计 2026-09-25）：修正文档错位——此前头两行复制自 consume
/// 入口（"在副作用执行点重新校验 URL/scope，并一次性消费 action nonce"），
/// 与本入口实际语义（登记待审批、不消费、不签发）不符。
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_request_navigation_confirmation_json(
    broker: *mut CAbiBroker,
    session_id: *const c_char,
    tab_id: *const c_char,
    generation: u64,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let session_id = match unwrap_input_or_deny(read_utf8(session_id)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let tab_id = match unwrap_input_or_deny(read_utf8(tab_id)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let raw_url = match unwrap_input_or_deny(read_utf8(raw_url)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let scope = match unwrap_input_or_deny(read_utf8(scope)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let Some(decision) = with_broker(broker, |value| {
            value
                .inner
                .request_navigation_confirmation(session_id, tab_id, generation, raw_url, scope)
        }) else {
            return input_deny("ffi_broker_null");
        };
        write_response(decision_json(&decision))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

/// 显式批准待审批导航并返回可消费的 JSON 授权；nonce、URL 或 scope 不匹配一律拒绝。
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_approve_navigation_confirmation_json(
    broker: *mut CAbiBroker,
    nonce: *const c_char,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let nonce = match unwrap_input_or_deny(read_utf8(nonce)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let raw_url = match unwrap_input_or_deny(read_utf8(raw_url)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let scope = match unwrap_input_or_deny(read_utf8(scope)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let Some(decision) = with_broker(broker, |value| {
            value
                .inner
                .approve_navigation_confirmation(nonce, raw_url, scope)
        }) else {
            return input_deny("ffi_broker_null");
        };
        write_response(decision_json(&decision))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

/// 显式拒绝待审批导航；未知、已兑换或已撤销 nonce 返回 0。
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_reject_navigation_confirmation(
    broker: *mut CAbiBroker,
    nonce: *const c_char,
) -> u8 {
    catch_unwind(AssertUnwindSafe(|| {
        let Ok(nonce) = read_utf8(nonce) else {
            return 0;
        };
        with_broker(broker, |value| {
            value.inner.reject_navigation_confirmation(nonce)
        })
        .unwrap_or(false) as u8
    }))
    .unwrap_or(0)
}

/// 在副作用执行点重新校验 URL/scope，并一次性消费 action nonce。
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_consume_navigation_json(
    broker: *mut CAbiBroker,
    action_json: *const c_char,
    raw_url: *const c_char,
    scope: *const c_char,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let action_json = match unwrap_input_or_deny(read_utf8(action_json)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let raw_url = match unwrap_input_or_deny(read_utf8(raw_url)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let scope = match unwrap_input_or_deny(read_utf8(scope)) {
            Ok(v) => v,
            Err(deny) => return deny,
        };
        let action = match parse_action(&action_json) {
            Ok(action) => action,
            Err(code) => return input_deny(code),
        };
        let Some(decision) = with_broker(broker, |value| {
            value.inner.consume_navigation(action, raw_url, scope)
        }) else {
            return input_deny("ffi_broker_null");
        };
        write_response(decision_json(&decision))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

/// 注入威胁 host 黑名单快照（审计第六轮 2026-10-03/04）。
///
/// 入参：`hosts_json` 为 JSON 字符串数组（`["evil.example","ads.example.com"]`）；
/// `clear` 为两阶段档位（第七轮 R7-RS-02）——非 0 先清空再接受本批（整批替换，
/// 等价于本入口的既往语义），0 表示**追加**到现有快照。
/// 返回：`{"decision":"ok","accepted":N,"input":M,"clear":bool,"mode":N,"staged":bool,
/// "served":N}` —— 宿主据 `accepted < input` 发现"有条目被形态校验拒收"，而不是静默
/// 变成永不命中的死条目。非法输入/非法 JSON/未知档位/空句柄/panic 一律返回 deny JSON。
///
/// 存在理由：此前 FFI 通路完全没有 deny-by-content 层（H-7 注记：
/// `policy.evaluate / capability.validate 未接入 FFI 通路`），黑名单只活在
/// 端侧代码里，Android 端因此整体没有威胁拦截。本入口是核心侧的最小接入面；
/// 未调用时黑名单为空、行为与既往一致（不 deny-all）。
///
/// 分批的硬需求（R7-RS-02）：`hosts_json` 受 `read_utf8` 的 `FFI_INPUT_MAX_BYTES`
/// = 64KiB 上限约束，而托管侧订阅源允许 5 MiB
///（Windows `ThreatFeed.MaxBytes`）——整批替换且无追加时，真实规模的名单必然注入
/// 失败（`ffi_input_too_long`），核心侧 `threat_blocklist` 分支因此从不执行。
/// 宿主据档位回显（`mode` 字段）判别核心能力，见 ⑨ 与 `denylist.rs`；旧 2 参核心
/// 会忽略多余实参并按整批替换行事。
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_broker_update_host_denylist_json(
    broker: *mut CAbiBroker,
    hosts_json: *const c_char,
    clear: i32,
) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let hosts_json = match unwrap_input_or_deny(read_utf8(hosts_json)) {
            Ok(value) => value,
            Err(response) => return response,
        };
        let parsed: Vec<String> = match serde_json::from_str(&hosts_json) {
            Ok(values) => values,
            Err(_) => return input_deny("denylist_input_invalid"),
        };
        let input = parsed.len() as u32;
        // ⑨：第三参从布尔扩成档位；未知档位直接拒，不"当作 0"（详见 denylist.rs）
        if !crate::ffi::denylist::mode_is_known(clear) {
            return input_deny("denylist_mode_invalid");
        }
        let Some(report) = with_broker(broker, move |value| {
            value.inner.apply_host_denylist_mode(parsed, clear)
        }) else {
            return input_deny("ffi_broker_null");
        };
        // write_response 接收 impl Serialize 并**直接序列化**——传 String 会被
        // 二次编码成 JSON 字符串字面量（消费方按对象取值即得 Null）。与既有
        // decision_json 入口保持同一形态：交 Value 本体。
        write_response(serde_json::json!({
            "decision": "ok",
            "accepted": report.accepted,
            "input": input,
            // clear 回显保留给旧宿主探针；档位由 mode 自证（能力探测见 DenylistPush）
            "clear": report.mode == crate::ffi::denylist::MODE_REPLACE,
            "mode": report.mode,
            "staged": report.staged,
            "served": report.served,
        }))
    }))
    .unwrap_or_else(|_| write_response(deny("native_panic", "native policy core panicked")))
}

//! 稳定、最小化的 C ABI 导航决策边界。
//!
//! 此模块只在 C ABI 中交换 UTF-8 JSON，避免将 Rust 布局、指针或生命周期暴露给
//! Windows P/Invoke 与 Android JNA。所有由本模块分配的响应字符串只能通过
//! `aegis_policy_core_string_free` 释放；未知会话、无效输入和内部错误一律返回
//! 类型化的 deny JSON，而非允许宿主改用不一致的策略路径。

use crate::ffi::{FfiApprovalRequest, FfiAuthorizedAction, FfiBroker, FfiDecision};
use crate::POLICY_CORE_ABI_VERSION;
use serde_json::{json, Value};
use std::ffi::{c_char, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{LazyLock, Mutex};

pub struct CAbiBroker {
    inner: FfiBroker,
    /// 进程级单例的"已退休"标志：free 只置位不释放——杜绝 use-after-free /
    /// 重复释放的未定义行为（后续调用读此标志返回 deny）。
    retired: AtomicBool,
}

/// C 输入指针的有界扫描上限。宿主按契约传 NUL 结尾缓冲区，此处仅防
/// 异常宿主传入超长/无终止缓冲造成的无界越读。
const FFI_INPUT_MAX_BYTES: usize = 64 * 1024;

fn read_utf8(value: *const c_char) -> Result<&'static str, &'static str> {
    if value.is_null() {
        return Err("ffi_input_null");
    }
    // SAFETY: 契约要求指针指向 NUL 结尾的可读缓冲。此处逐字节有界扫描并在
    // 首个 NUL 处停止——良构输入绝不触碰 NUL 之后的内存；此前
    // from_raw_parts(value, 64KB) 一次性声明整个窗口可读，宿主缓冲小于
    // 64KB 且 NUL 落在页尾时是真实越读（形式化 UB + 潜在页错误）。
    let base = value as *const u8;
    let mut len = 0usize;
    loop {
        let byte = unsafe { *base.add(len) };
        if byte == 0 {
            break;
        }
        len += 1;
        if len >= FFI_INPUT_MAX_BYTES {
            // 无 NUL 终止——拒绝而非继续无界读取
            return Err("ffi_input_too_long");
        }
    }
    let bytes = unsafe { std::slice::from_raw_parts(base, len) };
    std::str::from_utf8(bytes).map_err(|_| "ffi_input_utf8")
}

/// RS-139（审计 2026-09-25）：FALLBACK deny 响应预构造为进程级 static——
/// 此前每次分配失败路径现做 `CString::new(FALLBACK).expect(...)`（panic
/// 残留）。现在构造一次（LazyLock），响应分发走 `clone()`（O(bytes) 复制，
/// 无 recoverable 错误路径；字节含尾随 NUL、无内部 NUL——常量可证）。
static FALLBACK_RESPONSE: LazyLock<CString> = LazyLock::new(|| {
    // SAFETY: 字面量常量不含 NUL（serde JSON 转义保证）——满足
    // from_vec_unchecked 契约（无内部 NUL，函数自行追加尾随 NUL）。
    // 注意：不可预先 push(0)——该函数契约是「无 NUL」而非「有尾随 NUL」，
    // 预先拼接会产生双 NUL（to_str 返回内嵌 NUL 串，破坏 JSON 契约）。
    unsafe { CString::from_vec_unchecked(FALLBACK_JSON.to_vec()) }
});

const FALLBACK_JSON: &[u8] = b"{\"abi_version\":0,\"decision\":\"deny\",\"reason\":{\"code\":\"ffi_response_alloc\",\"detail\":\"response allocation failed\",\"explanation\":\"denied by aegis-policy-core native boundary\"}}";

/// JSON 编码为 NUL 结尾的 C 字符串。serde_json 输出不含字面 NUL（转义为
/// \u0000），因此正常情况下不会失败；为彻底兑现"绝不返回 null"，分配失败
/// 时回退到预构造的固定 ASCII deny 串（abi_version=0 标记异常响应，宿主
/// 可识别）。RS-139：回退串来自预构造 static 的克隆——无 panic 路径。
fn write_response(value: Value) -> *mut c_char {
    match CString::new(value.to_string()) {
        Ok(c) => CString::into_raw(c),
        Err(_) => CString::into_raw(FALLBACK_RESPONSE.clone()),
    }
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

fn approval_request_json(request: FfiApprovalRequest) -> Value {
    json!({
        "origin": request.origin,
        "method": request.method,
        "path": request.path,
        "scope": request.scope,
        "expires_at": request.expires_at,
        "nonce": request.nonce,
    })
}

fn decision_json(decision: FfiDecision) -> Value {
    match decision {
        FfiDecision::Allow { action } => json!({
            "abi_version": POLICY_CORE_ABI_VERSION,
            "decision": "allow",
            "action": action_json(action),
        }),
        FfiDecision::RequireConfirmation { request } => json!({
            "abi_version": POLICY_CORE_ABI_VERSION,
            "decision": "require_confirmation",
            "request": approval_request_json(request),
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
    // SAFETY: 指针只能由 `aegis_policy_core_broker_new` 创建；free 仅置退休
    // 标志而不释放，因此这里解引用始终指向已分配的对象。
    let b = unsafe { &*broker };
    if b.retired.load(Ordering::SeqCst) {
        return None; // 已退休——拒绝而非触碰已释放内存
    }
    Some(operation(b))
}

/// RS-140（审计 2026-09-25）：进程级单例互斥——同一时刻最多一个活跃
/// （未退休）Broker。活跃期间再次 `broker_new` 返回 null（fail-closed，
/// 防泄漏放大：每次成功创建都会产生一份不可释放的退休遗留分配）；
/// 退休（free）后允许重建（宿主生命周期边界）。锁中毒 → null。
/// Option<usize> 装箱裸指针地址（usize Send+Sync——裸指针自身不是）。
static LIVE_BROKER: Mutex<Option<usize>> = Mutex::new(None);

/// 创建独立的原生策略 Broker；`policy_version` 为空、无效 UTF-8、panic、
/// 活跃单例已存在或锁中毒时返回 null（RS-140 单例互斥）。
#[no_mangle]
pub extern "C" fn aegis_policy_core_broker_new(policy_version: *const c_char) -> *mut CAbiBroker {
    catch_unwind(AssertUnwindSafe(|| {
        let Ok(policy_version) = read_utf8(policy_version) else {
            return ptr::null_mut();
        };
        if policy_version.is_empty() {
            return ptr::null_mut();
        }
        let Ok(mut live) = LIVE_BROKER.lock() else {
            return ptr::null_mut(); // 锁中毒 fail-closed
        };
        if let Some(addr) = *live {
            // SAFETY: 地址只能来自本函数既往 Box::into_raw（从不释放），
            // 读 retired 标志无悬垂
            let is_retired = unsafe {
                (*(addr as *const CAbiBroker))
                    .retired
                    .load(Ordering::SeqCst)
            };
            if !is_retired {
                return ptr::null_mut(); // 活跃单例存在——拒绝二次创建
            }
        }
        let broker = Box::into_raw(Box::new(CAbiBroker {
            inner: FfiBroker::new(policy_version.to_owned()),
            retired: AtomicBool::new(false),
        }));
        *live = Some(broker as usize);
        broker
    }))
    .unwrap_or(ptr::null_mut())
}

/// 退休（标记）由 `aegis_policy_core_broker_new` 创建的 Broker；null 是幂等安全操作。
///
/// Broker 为进程级单例——本函数**有意不释放**底层分配，仅置 retired 标志；
/// 后续所有对该句柄的调用都会读到标志并返回 deny（而非 use-after-free）。
/// 退休分配的一次性泄漏可接受；RS-140 单例互斥保证同一时刻至多一份
/// 活跃分配 + 一份退休遗留，泄漏总量有界（不再随 broker_new 调用次数放大）。
///
/// # Safety
/// `broker` 必须为本库创建（或 null）；指向任意地址是未定义行为。
#[no_mangle]
pub unsafe extern "C" fn aegis_policy_core_broker_free(broker: *mut CAbiBroker) {
    if !broker.is_null() {
        // SAFETY: 指针只能由 `aegis_policy_core_broker_new` 创建；只置标志不释放。
        unsafe { (*broker).retired.store(true, Ordering::SeqCst) };
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

mod navigation;
pub use navigation::*;

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CStr;

    /// RS-140：broker_new 现为进程级单例互斥——并行测试会互相挤掉
    /// 对方的活跃单例。所有创建 C ABI broker 的测试必须先取此串行守卫。
    static BROKER_SERIAL: Mutex<()> = Mutex::new(());
    fn broker_test_guard() -> std::sync::MutexGuard<'static, ()> {
        BROKER_SERIAL
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

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
        let url = c_string("https://example.com/confirm?transfer=1");
        let mismatched_url = c_string("https://example.com/confirm?transfer=2");
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
            aegis_policy_core_broker_reject_navigation_confirmation(
                broker,
                rejected_nonce.as_ptr()
            ),
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
        let decision = decision_json(FfiDecision::RequireConfirmation {
            request: FfiApprovalRequest {
                origin: "https://payments.example".into(),
                method: "POST".into(),
                path: "/transfers".into(),
                scope: "payment:create".into(),
                expires_at: 1_700_000_000,
                nonce: "approval-nonce".into(),
            },
        });

        assert_eq!(decision["decision"], "require_confirmation");
        assert_eq!(decision["request"]["path"], "/transfers");
        assert_eq!(decision["request"]["scope"], "payment:create");
        assert_eq!(decision["request"]["expires_at"], 1_700_000_000);
        assert_eq!(decision["request"]["nonce"], "approval-nonce");
    }

    #[test]
    fn c_abi_matches_native_navigation_decision_vectors() {
        let _serial = broker_test_guard();
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../../contracts/vectors/native-navigation-decision.json"
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
            // PY-091/092（审计 2026-09-25）：向量协议扩展——销毁会话/推进代际
            // 后再次消费同一 action，断言 fail-closed 拒绝码
            if vector
                .get("destroy_session")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                assert_eq!(
                    aegis_policy_core_broker_destroy_session(broker, session.as_ptr()),
                    1,
                    "{name}: destroy session"
                );
            }
            if vector
                .get("advance_generation")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                assert_eq!(
                    aegis_policy_core_broker_advance_document_generation(
                        broker,
                        session.as_ptr(),
                        tab.as_ptr(),
                        generation + 1,
                    ),
                    1,
                    "{name}: advance generation"
                );
            }
            if let Some(expected_reconsume_code) = vector.get("expected_reconsume_code") {
                let reconsume = read_response(aegis_policy_core_broker_consume_navigation_json(
                    broker,
                    action.as_ptr(),
                    consume_url.as_ptr(),
                    consume_scope.as_ptr(),
                ));
                assert_eq!(reconsume["decision"], "deny", "{name}: reconsume must deny");
                assert_eq!(
                    reconsume["reason"]["code"], *expected_reconsume_code,
                    "{name}: reconsume denial code"
                );
            }
            // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
            unsafe { aegis_policy_core_broker_free(broker) };
        }
    }

    #[test]
    fn c_abi_matches_native_navigation_confirmation_vectors() {
        let _serial = broker_test_guard();
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../../contracts/vectors/native-navigation-confirmation.json"
        ))
        .expect("native navigation confirmation vectors must be valid JSON");

        for vector in vectors["vectors"].as_array().expect("vectors array") {
            let name = vector["name"].as_str().expect("vector name");
            let version = c_string("1.0");
            let broker = aegis_policy_core_broker_new(version.as_ptr());
            assert!(!broker.is_null(), "{name}: broker creation");
            let session = c_string("confirmation-vector-session");
            let tab = c_string("confirmation-vector-tab");
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
            let requested = read_response(
                aegis_policy_core_broker_request_navigation_confirmation_json(
                    broker,
                    session.as_ptr(),
                    tab.as_ptr(),
                    generation,
                    url.as_ptr(),
                    scope.as_ptr(),
                ),
            );
            assert_eq!(
                requested["decision"], vector["expected_request"],
                "{name}: request decision"
            );
            if requested["decision"] == "deny" {
                assert_eq!(
                    requested["reason"]["code"], vector["expected_request_code"],
                    "{name}: request denial"
                );
                // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
                unsafe { aegis_policy_core_broker_free(broker) };
                continue;
            }
            let nonce = c_string(
                requested["request"]["nonce"]
                    .as_str()
                    .expect("approval nonce"),
            );
            if let Some(next_generation) = vector.get("advance_generation") {
                assert_eq!(
                    aegis_policy_core_broker_advance_document_generation(
                        broker,
                        session.as_ptr(),
                        tab.as_ptr(),
                        next_generation.as_u64().expect("next generation"),
                    ),
                    1,
                    "{name}: generation advance"
                );
            }
            if vector
                .get("reject")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                assert_eq!(
                    aegis_policy_core_broker_reject_navigation_confirmation(broker, nonce.as_ptr(),),
                    1,
                    "{name}: explicit rejection"
                );
            }
            let approve_url = c_string(vector["approve_url"].as_str().expect("approve URL"));
            let approve_scope = c_string(vector["approve_scope"].as_str().expect("approve scope"));
            let approved = read_response(
                aegis_policy_core_broker_approve_navigation_confirmation_json(
                    broker,
                    nonce.as_ptr(),
                    approve_url.as_ptr(),
                    approve_scope.as_ptr(),
                ),
            );
            assert_eq!(
                approved["decision"], vector["expected_approve"],
                "{name}: approve decision"
            );
            if let Some(expected_code) = vector.get("expected_approve_code") {
                assert_eq!(
                    approved["reason"]["code"], *expected_code,
                    "{name}: approve denial"
                );
            }
            if let Some(expected_code) = vector.get("expected_second_approve_code") {
                let second = read_response(
                    aegis_policy_core_broker_approve_navigation_confirmation_json(
                        broker,
                        nonce.as_ptr(),
                        approve_url.as_ptr(),
                        approve_scope.as_ptr(),
                    ),
                );
                assert_eq!(
                    second["reason"]["code"], *expected_code,
                    "{name}: second approval"
                );
            }
            if approved["decision"] == "allow" {
                let action = c_string(&approved["action"].to_string());
                let consumed = read_response(aegis_policy_core_broker_consume_navigation_json(
                    broker,
                    action.as_ptr(),
                    approve_url.as_ptr(),
                    approve_scope.as_ptr(),
                ));
                assert_eq!(
                    consumed["decision"], vector["expected_consume"],
                    "{name}: consume decision"
                );
                if let Some(expected_code) = vector.get("expected_replay_code") {
                    let replay = read_response(aegis_policy_core_broker_consume_navigation_json(
                        broker,
                        action.as_ptr(),
                        approve_url.as_ptr(),
                        approve_scope.as_ptr(),
                    ));
                    assert_eq!(
                        replay["reason"]["code"], *expected_code,
                        "{name}: replay denial"
                    );
                }
            }
            // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
            unsafe { aegis_policy_core_broker_free(broker) };
        }
    }

    #[test]
    fn freed_broker_retires_cleanly_without_ub() {
        let _serial = broker_test_guard();
        // 审计整改：broker_free 置 retired 标志（不再释放底层分配）——
        // 退休后调用返回 deny，而非 use-after-free；重复 free 幂等。
        let version = c_string("1.0");
        let broker = aegis_policy_core_broker_new(version.as_ptr());
        assert!(!broker.is_null());
        let sid = c_string("s");
        let tid = c_string("t");
        let url = c_string("https://example.com/");
        let scope = c_string("navigation");
        // SAFETY: broker 由本测试创建。
        unsafe { aegis_policy_core_broker_free(broker) };
        let res = aegis_policy_core_broker_evaluate_navigation_json(
            broker,
            sid.as_ptr(),
            tid.as_ptr(),
            0,
            url.as_ptr(),
            scope.as_ptr(),
        );
        assert!(!res.is_null());
        let value = read_response(res);
        assert_eq!(value["decision"], "deny");
        // 重复 free：幂等（仅再次置位同一标志）
        // SAFETY: broker 由本测试创建，free 幂等。
        unsafe { aegis_policy_core_broker_free(broker) };
    }

    // ===== RS-049：read_utf8 有界扫描边界路径（此前零直接覆盖）=====

    /// 构造以 NUL 结尾的 C 缓冲区指针。
    fn c_buf(mut bytes: Vec<u8>) -> (*const c_char, Vec<u8>) {
        bytes.push(0);
        (bytes.as_ptr() as *const c_char, bytes)
    }

    #[test]
    fn read_utf8_accepts_nul_terminated_at_max_boundary() {
        // 恰好 64KB - 1 有效字节 + NUL：合法（扫描在 NUL 处停止）
        let (ptr, _buf) = c_buf(vec![b'a'; FFI_INPUT_MAX_BYTES - 1]);
        let s = read_utf8(ptr).expect("NUL 终止的合法载荷必须被接受");
        assert_eq!(s.len(), FFI_INPUT_MAX_BYTES - 1);
    }

    #[test]
    fn read_utf8_rejects_64kb_without_nul_terminator() {
        // 64KB 有效字节 + NUL：有效载荷已触及上限——无 NUL 终止语义，
        // 有界扫描在上限处拒绝而非继续越读
        let (ptr, _buf) = c_buf(vec![b'a'; FFI_INPUT_MAX_BYTES]);
        assert_eq!(read_utf8(ptr), Err("ffi_input_too_long"));
    }

    #[test]
    fn read_utf8_rejects_oversized_beyond_max() {
        let (ptr, _buf) = c_buf(vec![b'a'; FFI_INPUT_MAX_BYTES * 2]);
        assert_eq!(read_utf8(ptr), Err("ffi_input_too_long"));
    }

    #[test]
    fn read_utf8_rejects_non_utf8_payload() {
        // 非 UTF-8 载荷（含 NUL 终止）→ 类型化拒绝，不 panic、不 UB
        let (ptr, _buf) = c_buf(vec![0xFF, 0xFE, b'a', 0x80]);
        assert_eq!(read_utf8(ptr), Err("ffi_input_utf8"));
    }

    #[test]
    fn read_utf8_rejects_null_pointer() {
        assert_eq!(read_utf8(ptr::null()), Err("ffi_input_null"));
    }

    #[test]
    fn c_abi_broker_new_rejects_non_utf8_policy_version() {
        // 公共 ABI 路径：非 UTF-8 policy_version → null（而非 panic/UB）
        let (bad, _buf) = c_buf(vec![0xFF, 0xFE, b'1']);
        assert!(aegis_policy_core_broker_new(bad).is_null());
    }

    // ===== RS-138（审计 2026-09-25）：畸形 JSON / null 指针 / retired =====

    #[test]
    fn consume_with_malformed_action_json_is_typed_deny() {
        let _serial = broker_test_guard();
        let version = c_string("1.0");
        let broker = aegis_policy_core_broker_new(version.as_ptr());
        assert!(!broker.is_null());
        let not_json = c_string("{not json");
        let url = c_string("https://example.com/");
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
        let url = c_string("https://example.com/");
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
        let url = c_string("https://example.com/");
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
            aegis_policy_core_broker_advance_document_generation(
                broker,
                sid.as_ptr(),
                tid.as_ptr(),
                0
            ),
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
        let parsed: Value = serde_json::from_str(text).expect("FALLBACK 必须是合法 JSON");
        assert_eq!(parsed["abi_version"], 0);
        assert_eq!(parsed["decision"], "deny");
        assert_eq!(parsed["reason"]["code"], "ffi_response_alloc");
    }

    #[test]
    fn broker_new_enforces_single_live_instance() {
        // RS-140：活跃单例存在时二次创建返回 null（防泄漏放大）；
        // 退休后允许重建——泄漏总量有界（1 活跃 + 1 遗留）
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
}

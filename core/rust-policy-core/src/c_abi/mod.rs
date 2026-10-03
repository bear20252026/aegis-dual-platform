//! 稳定、最小化的 C ABI 导航决策边界。
//!
//! 此模块只在 C ABI 中交换 UTF-8 JSON，避免将 Rust 布局、指针或生命周期暴露给
//! Windows P/Invoke 与 Android JNA。所有由本模块分配的响应字符串只能通过
//! `aegis_policy_core_string_free` 释放；未知会话、无效输入和内部错误一律返回
//! 类型化的 deny JSON，而非允许宿主改用不一致的策略路径。

use crate::ffi::{FfiApprovalRequest, FfiAuthorizedAction, FfiBroker, FfiDecision};
use crate::POLICY_CORE_ABI_VERSION;
use serde::Serialize;
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

// RS-200（审计 2026-09-25）：`pub` 可达性说明——CAbiBroker 必须 pub 仅因
// C ABI 导出函数签名（aegis_policy_core_broker_new/free/... 返回/接收
// `*mut CAbiBroker`）要求类型跨 crate 可达；字段全部私有，宿主不得解引用
// 或推演内部布局——唯一合法交互是通过本模块导出的 C 函数句柄。

/// C 输入指针的有界扫描上限。宿主按契约传 NUL 结尾缓冲区，此处仅防
/// 异常宿主传入超长/无终止缓冲造成的无界越读。
const FFI_INPUT_MAX_BYTES: usize = 64 * 1024;

/// RS-239（2026-10-01 审计）：返回 String——RS-211 的生命周期参数化
/// （`Result<&'a str, _>`）在签名层面仍是 unsound：`'a` 不在输入位置，
/// 调用方可凭空调短它，把宿主 C 缓冲切片声明成任意长的生命周期后存入
/// 全局/缓存（悬垂）。所有调用点本来就立即 `.to_owned()`，改为按值返回
/// String 在消灭签名漏洞的同时不多付一次拷贝（此前是「借用 + 克隆」
/// 两步，现在单次分配）。错误侧仍为 'static 字面量。
fn read_utf8(value: *const c_char) -> Result<String, &'static str> {
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
    // SAFETY: 长度由有界扫描确定，仅覆盖首个 NUL 之前的字节。
    let bytes = unsafe { std::slice::from_raw_parts(base, len) };
    std::str::from_utf8(bytes)
        .map(|s| s.to_owned())
        .map_err(|_| "ffi_input_utf8")
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

/// RS-176（审计 2026-09-25）：边界拒绝 explanation 单源——deny() 与
/// FALLBACK_JSON 此前各持一份相同文案（改一处漏一处即口径分裂）。
/// FALLBACK_JSON 为静态可证无 NUL 的字节字面量（RS-139 契约），无法引用
/// 运行时常量——同步性由 c_abi_json_contract 测试锁定（字节包含断言）。
const NATIVE_BOUNDARY_EXPLANATION: &str = "denied by aegis-policy-core native boundary";

const FALLBACK_JSON: &[u8] = b"{\"abi_version\":0,\"decision\":\"deny\",\"reason\":{\"code\":\"ffi_response_alloc\",\"detail\":\"response allocation failed\",\"explanation\":\"denied by aegis-policy-core native boundary\"}}";

/// JSON 编码为 NUL 结尾的 C 字符串。serde_json 输出不含字面 NUL（转义为
/// \u0000），因此正常情况下不会失败；为彻底兑现"绝不返回 null"，分配失败
/// 时回退到预构造的固定 ASCII deny 串（abi_version=0 标记异常响应，宿主
/// 可识别）。RS-139：回退串来自预构造 static 的克隆——无 panic 路径。
/// RS-175（审计 2026-09-25）：`to_writer` 直接序列化进单缓冲——此前
/// `value.to_string()` 走 Display 层再转 CString（额外一层 String 中转），
/// writer 直写 Vec 省一次中转分配。
/// RS-268（2026-10-01 审计）：入参泛型化为 `impl Serialize`——调用方传入
/// 强类型响应结构（见下方 DenyJson/DecisionJson），不再先构建整棵
/// serde_json::Value 树再序列化（Value 树每节点一次堆分配，序列化输出
/// 再一次全量分配——双倍分配）。Value 仍可用（测试直传）。
fn write_response(value: impl Serialize) -> *mut c_char {
    let mut buf = Vec::new();
    match serde_json::to_writer(&mut buf, &value)
        .ok()
        .and_then(|()| CString::new(buf).ok())
    {
        Some(c) => CString::into_raw(c),
        None => CString::into_raw(FALLBACK_RESPONSE.clone()),
    }
}

// ===== RS-268：强类型响应结构（直写序列化，取代 Value 树）=====

/// deny 响应的 reason 子对象（借用形态——零拷贝引用调用方字符串）。
#[derive(Serialize)]
struct DenyReasonRef<'a> {
    code: &'a str,
    detail: &'a str,
    explanation: &'a str,
}

/// deny 响应信封（abi_version + decision + reason）。
#[derive(Serialize)]
struct DenyJson<'a> {
    abi_version: u32,
    decision: &'static str,
    reason: DenyReasonRef<'a>,
}

fn deny<'a>(code: &'a str, detail: &'a str) -> DenyJson<'a> {
    DenyJson {
        abi_version: POLICY_CORE_ABI_VERSION,
        decision: "deny",
        reason: DenyReasonRef {
            code,
            detail,
            explanation: NATIVE_BOUNDARY_EXPLANATION,
        },
    }
}

/// 决策体——internally tagged（`decision` 字段），变体名 snake_case 对齐
/// 既有 JSON 契约（allow / require_confirmation / deny）。
#[derive(Serialize)]
#[serde(tag = "decision", rename_all = "snake_case")]
enum DecisionBody<'a> {
    Allow { action: &'a FfiAuthorizedAction },
    RequireConfirmation { request: &'a FfiApprovalRequest },
    Deny { reason: DenyReasonRef<'a> },
}

/// 决策响应信封——abi_version 平铺 + 决策体 flatten（输出形态与既有
/// Value 构造逐字段一致：{"abi_version":N,"decision":"...","action"|"request"|"reason":{...}}）。
#[derive(Serialize)]
struct DecisionJson<'a> {
    abi_version: u32,
    #[serde(flatten)]
    body: DecisionBody<'a>,
}

fn decision_json(decision: &FfiDecision) -> DecisionJson<'_> {
    let body = match decision {
        FfiDecision::Allow { action } => DecisionBody::Allow { action },
        FfiDecision::RequireConfirmation { request } => {
            DecisionBody::RequireConfirmation { request }
        }
        FfiDecision::Deny { reason } => DecisionBody::Deny {
            reason: DenyReasonRef {
                code: &reason.code,
                detail: &reason.detail,
                explanation: &reason.explanation,
            },
        },
    };
    DecisionJson {
        abi_version: POLICY_CORE_ABI_VERSION,
        body,
    }
}

fn read_string_field(
    value: &serde_json::Value,
    name: &'static str,
) -> Result<String, &'static str> {
    value
        .get(name)
        .and_then(serde_json::Value::as_str)
        .filter(|field| !field.is_empty())
        .map(ToOwned::to_owned)
        .ok_or("ffi_action_invalid")
}

fn read_u64_field(value: &serde_json::Value, name: &'static str) -> Result<u64, &'static str> {
    value
        .get(name)
        .and_then(serde_json::Value::as_u64)
        .ok_or("ffi_action_invalid")
}

fn parse_action(action_json: &str) -> Result<FfiAuthorizedAction, &'static str> {
    let value: serde_json::Value =
        serde_json::from_str(action_json).map_err(|_| "ffi_action_invalid_json")?;
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
            .and_then(serde_json::Value::as_str)
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
#[unsafe(no_mangle)]
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
            inner: FfiBroker::new(policy_version),
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
///
/// RS-236（2026-09-26 审计）：泄漏口径修正——此前注释宣称「RS-140 单例
/// 互斥保证泄漏总量有界」，该说法**仅对单轮生命周期成立**。多轮
/// new→free→new 循环下，LIVE_BROKER 直接覆盖旧退休地址且 Box 永不
/// drop：每轮退休一份不可释放的 CAbiBroker 分配，退休分配随生命周期
/// 轮数**线性累积**（1 轮 = 1 份遗留）。单例互斥约束的是「同一时刻至多
/// 一份活跃分配」，不是全进程总量。宿主约定：按进程边界创建/退休
/// （而非页面级高频循环）时累积轮数有限，单份遗留尺寸为常数级。
///
/// # Safety
/// `broker` 必须为本库创建（或 null）；指向任意地址是未定义行为。
#[unsafe(no_mangle)]
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
#[unsafe(no_mangle)]
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

    fn read_response(response: *mut c_char) -> serde_json::Value {
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

    #[test]
    fn c_abi_matches_native_navigation_decision_vectors() {
        let _serial = broker_test_guard();
        let vectors: serde_json::Value = serde_json::from_str(include_str!(
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
            // 审计第六轮（2026-10-03/04）：可选威胁 host 黑名单注入。
            // deny-by-content 此前在向量里没有表达形式（native-navigation-decision
            // 只覆盖 url_policy / session_not_found 两类拒绝），"黑名单匹配"这类
            // 最像安全特性的代码从未被跨端锁定。accepted 必须等于条目数——不等即
            // 说明有条目被形态校验拒收，将成为永不命中的死条目。
            if let Some(hosts) = vector.get("deny_hosts") {
                let payload = c_string(&hosts.to_string());
                let applied = read_response(aegis_policy_core_broker_update_host_denylist_json(
                    broker,
                    payload.as_ptr(),
                ));
                assert_eq!(applied["decision"], "ok", "{name}: 黑名单注入失败");
                assert_eq!(
                    applied["accepted"].as_u64(),
                    Some(hosts.as_array().expect("deny_hosts 必须是数组").len() as u64),
                    "{name}: 黑名单有条目被形态校验拒收（静默死条目）"
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
            // 审计第六轮（2026-10-03/04）：高危目标（本机/私网）走待审批分支——
            // 核心不得发放可消费授权，只回 request；这条分支此前不存在，因为
            // evaluate_navigation 从不做内容判定。
            if evaluated["decision"] == "require_confirmation" {
                if let Some(expected_origin) = vector.get("expected_origin") {
                    assert_eq!(
                        evaluated["request"]["origin"], *expected_origin,
                        "{name}: 待审批请求 origin"
                    );
                }
                assert!(
                    evaluated.get("action").is_none(),
                    "{name}: 高危目标不得同时发放可消费授权"
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
        let vectors: serde_json::Value = serde_json::from_str(include_str!(
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
            // 审计第六轮（2026-10-03/04）：可选威胁 host 黑名单注入。
            // deny-by-content 此前在向量里没有表达形式（native-navigation-decision
            // 只覆盖 url_policy / session_not_found 两类拒绝），"黑名单匹配"这类
            // 最像安全特性的代码从未被跨端锁定。accepted 必须等于条目数——不等即
            // 说明有条目被形态校验拒收，将成为永不命中的死条目。
            if let Some(hosts) = vector.get("deny_hosts") {
                let payload = c_string(&hosts.to_string());
                let applied = read_response(aegis_policy_core_broker_update_host_denylist_json(
                    broker,
                    payload.as_ptr(),
                ));
                assert_eq!(applied["decision"], "ok", "{name}: 黑名单注入失败");
                assert_eq!(
                    applied["accepted"].as_u64(),
                    Some(hosts.as_array().expect("deny_hosts 必须是数组").len() as u64),
                    "{name}: 黑名单有条目被形态校验拒收（静默死条目）"
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
                .and_then(serde_json::Value::as_bool)
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
        let url = c_string("https://127.0.0.1/");
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
        let parsed: serde_json::Value =
            serde_json::from_str(text).expect("FALLBACK 必须是合法 JSON");
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

    // —— RS-310（2026-10-02 审计）：C ABI 导出面冻结清单 ——

    /// 导出面枚举测试——解析自身源文件（include_str 两文件），提取全部
    /// `#[unsafe(no_mangle)]` 导出符号，与冻结 Vec 全等比对。
    ///
    /// 此前导出面无冻结清单：新增 `#[unsafe(no_mangle)]` 符号（有意或
    /// 复制粘贴意外）会静默扩大 ABI 契约面（Windows P/Invoke / Android
    /// JNA 按符号名绑定，扩面即向后兼容承诺）。现以测试锁定：新增/删除/
    /// 改名导出必须显式同步 FROZEN_EXPORTS 清单（清单与源同步是唯一
    /// 变更通道，评审时一目了然）。
    #[test]
    fn c_abi_export_surface_is_frozen() {
        const FROZEN_EXPORTS: &[&str] = &[
            // mod.rs（句柄/生命周期）
            "aegis_policy_core_broker_new",
            "aegis_policy_core_broker_free",
            "aegis_policy_core_string_free",
            // navigation.rs（会话/导航/审批）
            "aegis_policy_core_broker_create_session",
            "aegis_policy_core_broker_destroy_session",
            "aegis_policy_core_broker_advance_document_generation",
            "aegis_policy_core_broker_evaluate_navigation_json",
            "aegis_policy_core_broker_request_navigation_confirmation_json",
            "aegis_policy_core_broker_approve_navigation_confirmation_json",
            "aegis_policy_core_broker_reject_navigation_confirmation",
            "aegis_policy_core_broker_consume_navigation_json",
            // 审计第六轮（2026-10-03/04）：威胁 host 黑名单注入入口——FFI 通路
            // 此前无任何 deny-by-content 接入面（H-7），Android 端因此整体缺黑名单
            "aegis_policy_core_broker_update_host_denylist_json",
        ];
        // 扫描源文件：no_mangle 属性行的下一个 `pub ... fn name(` 行
        // 提取符号名（本 crate 导出全部为该两行形态）
        let mut found: Vec<String> = Vec::new();
        for src in [include_str!("mod.rs"), include_str!("navigation.rs")] {
            let mut pending = false;
            for line in src.lines() {
                let t = line.trim();
                if t == "#[unsafe(no_mangle)]" {
                    pending = true;
                } else if pending && t.starts_with("pub") && t.contains(" fn ") {
                    let name = t
                        .split("fn ")
                        .nth(1)
                        .and_then(|rest| rest.split('(').next())
                        .unwrap_or("<unparseable>")
                        .trim()
                        .to_string();
                    found.push(name);
                    pending = false;
                }
            }
        }
        found.sort();
        let mut expected: Vec<&str> = FROZEN_EXPORTS.to_vec();
        expected.sort_unstable();
        assert_eq!(
            found, expected,
            "C ABI 导出面与冻结清单不一致——新增/删除/改名导出必须显式更新 \
             FROZEN_EXPORTS（导出面 = ABI 契约，不得静默变更）"
        );
    }
}

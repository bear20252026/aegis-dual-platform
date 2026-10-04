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
mod tests;

use super::super::*;

pub(super) use std::ffi::CStr;

/// RS-140：broker_new 现为进程级单例互斥——并行测试会互相挤掉
/// 对方的活跃单例。所有创建 C ABI broker 的测试必须先取此串行守卫。
pub(super) static BROKER_SERIAL: Mutex<()> = Mutex::new(());
pub(super) fn broker_test_guard() -> std::sync::MutexGuard<'static, ()> {
    BROKER_SERIAL
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

pub(super) fn c_string(value: &str) -> CString {
    CString::new(value).expect("test input must not contain NUL")
}

pub(super) fn read_response(response: *mut c_char) -> serde_json::Value {
    assert!(!response.is_null());
    // SAFETY: response 由被测 C ABI 入口创建且尚未释放，此处只读取。
    let text = unsafe { CStr::from_ptr(response) }
        .to_str()
        .expect("response must be valid UTF-8")
        .to_owned();
    // SAFETY: response 由被测 C ABI 入口创建，每个测试仅释放一次。
    unsafe { aegis_policy_core_string_free(response) };
    serde_json::from_str(&text).expect("response must be valid JSON")
}

// ── 黑名单注入的三个共用探针 ─────────────────────────────────────────────
// 上收到本文件（R9-B34 / Q29）：档位面（`denylist_modes.rs`）与分批规模面
//（`buffer_boundaries.rs`）判的是同一个入口 `aegis_policy_core_broker_update_host_denylist_json`，
// 各留一份 helper 的话，「应答字段少一个」这类回归只会从其中一份里漏掉。

/// 生成 count 条形态合法、互不重复的 host 的 JSON 数组载荷。
pub(super) fn denylist_payload(prefix: &str, count: usize) -> String {
    let hosts = (0..count)
        .map(|index| format!("{prefix}-{index}.deny.example"))
        .map(serde_json::Value::from)
        .collect::<Vec<_>>();
    serde_json::Value::Array(hosts).to_string()
}

/// 注入一批并取应答（`clear` 位现为**档位**：0 追加 / 1 整批替换 / 2 开会话 / 3 提交）。
pub(super) fn push_denylist(
    broker: *mut CAbiBroker,
    payload: &str,
    clear: i32,
) -> serde_json::Value {
    let buffer = c_string(payload);
    read_response(aegis_policy_core_broker_update_host_denylist_json(
        broker,
        buffer.as_ptr(),
        clear,
    ))
}

/// 导航裁决的应答（黑名单命中的行为探针）。
pub(super) fn evaluate_code(broker: *mut CAbiBroker, url: &str) -> serde_json::Value {
    let session = c_string("chunk-session");
    let tab = c_string("chunk-tab");
    assert_eq!(
        aegis_policy_core_broker_create_session(broker, session.as_ptr(), tab.as_ptr(), 0, 60),
        1,
        "session registration"
    );
    let scope = c_string("navigation");
    let target = c_string(url);
    read_response(aegis_policy_core_broker_evaluate_navigation_json(
        broker,
        session.as_ptr(),
        tab.as_ptr(),
        0,
        target.as_ptr(),
        scope.as_ptr(),
    ))
}

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

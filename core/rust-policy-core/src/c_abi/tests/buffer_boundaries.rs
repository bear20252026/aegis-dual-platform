use super::super::*;

use super::common::*;

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

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

// ===== R7-RS-02（审计第七轮 2026-10-04）：host 黑名单注入入口的行为面 =====
// 上面几条只直接测 `read_utf8`，而真实规模下必然越界的是**本入口**
//（托管侧订阅源上限 5 MiB ≫ FFI_INPUT_MAX_BYTES 64KiB），注入失败即核心侧
// `threat_blocklist` 分支整会话不执行——缺的不是上限，是分批通道。

/// 生成 count 条形态合法、互不重复的 host 的 JSON 数组载荷。
fn denylist_payload(prefix: &str, count: usize) -> String {
    let hosts = (0..count)
        .map(|index| format!("{prefix}-{index}.deny.example"))
        .map(serde_json::Value::from)
        .collect::<Vec<_>>();
    serde_json::Value::Array(hosts).to_string()
}

/// 注入一批并取应答（`clear` 透传两阶段标志）。
fn push_denylist(broker: *mut CAbiBroker, payload: &str, clear: i32) -> serde_json::Value {
    let buffer = c_string(payload);
    read_response(aegis_policy_core_broker_update_host_denylist_json(
        broker,
        buffer.as_ptr(),
        clear,
    ))
}

/// 导航裁决的拒绝码（黑名单命中的行为探针）。
fn evaluate_code(broker: *mut CAbiBroker, url: &str) -> serde_json::Value {
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

#[test]
fn host_denylist_entry_rejects_oversized_single_batch() {
    // 入口级（不是 read_utf8 级）负例：单批载荷越过 64KiB 上限必须拿到类型化
    // 拒绝，且**不得**留下部分快照——静默截断等于"名单看起来在工作"
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let oversize = denylist_payload("oversize", 6_000);
    assert!(
        oversize.len() > FFI_INPUT_MAX_BYTES,
        "用例载荷必须真的越过上限（当前 {} 字节）",
        oversize.len()
    );
    let rejected = push_denylist(broker, &oversize, 1);
    assert_eq!(rejected["decision"], "deny", "超长单批必须被拒");
    assert_eq!(rejected["reason"]["code"], "ffi_input_too_long");
    // 被拒的那一批一条都没进来（无部分快照）
    assert_eq!(
        evaluate_code(broker, "https://oversize-0.deny.example/")["decision"],
        "allow",
        "被拒载荷不得留下部分快照"
    );
    // SAFETY: broker 由本测试创建，且在此后不再使用。
    unsafe { aegis_policy_core_broker_free(broker) };
}

#[test]
fn host_denylist_appends_chunks_after_the_clearing_batch() {
    // 两阶段：首批 clear=1 建立快照，后续 clear=0 追加。整批替换语义下
    // 第二批会把第一批**抹掉**——两批 host 必须都仍在核心黑名单内
    let _serial = broker_test_guard();
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(!broker.is_null());
    let first = denylist_payload("first", 1_200);
    let second = denylist_payload("second", 1_200);
    // 分批的前提：每批都必须在 64KiB 上限内（否则只是换个姿势失败）
    assert!(first.len() < FFI_INPUT_MAX_BYTES && second.len() < FFI_INPUT_MAX_BYTES);
    for (batch, clear) in [(&first, 1), (&second, 0)] {
        let applied = push_denylist(broker, batch, clear);
        assert_eq!(applied["decision"], "ok", "分批注入不得被拒");
        assert_eq!(
            applied["accepted"], applied["input"],
            "本批条目被形态校验拒收（clear={clear}）"
        );
        // clear 回显是宿主侧唯一的"所加载核心确有本参数"探针（旧 2 参核心
        // 会忽略多余实参、应答里不带该字段）
        assert!(applied.get("clear").is_some(), "应答必须回显 clear 档位");
        assert_eq!(applied["clear"], serde_json::Value::Bool(clear != 0));
    }
    for url in [
        "https://first-0.deny.example/",
        "https://first-1199.deny.example/",
        "https://second-0.deny.example/",
    ] {
        let decision = evaluate_code(broker, url);
        assert_eq!(decision["decision"], "deny", "{url} 应命中核心黑名单");
        assert_eq!(decision["reason"]["code"], "threat_blocklist");
    }
    // clear=1 仍保留"整批替换"能力（旧语义不变）：第三批清空前两批
    let replaced = push_denylist(broker, &denylist_payload("third", 3), 1);
    assert_eq!(replaced["accepted"], 3);
    assert_eq!(
        evaluate_code(broker, "https://first-0.deny.example/")["decision"],
        "allow",
        "clear=1 必须丢弃此前快照"
    );
    assert_eq!(
        evaluate_code(broker, "https://third-0.deny.example/")["decision"],
        "deny"
    );
    // SAFETY: broker 由本测试创建，且在此后不再使用。
    unsafe { aegis_policy_core_broker_free(broker) };
}

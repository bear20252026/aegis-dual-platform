//! R8-RS-13（第八轮登记 2026-10-04，第九轮 R9-B61 落地）：宿主直传的定长种子
//! 必须**先判长度再解码**。
//!
//! 缺陷形态：`hex_seed_to_bytes` 把 `util::hex_decode` 放在长度判定之前，而
//! `hex_decode` 对任意偶数长度先 `Vec::with_capacity(len/2)` 再全量扫描——
//! uniffi 面（`build_fingerprint_pipeline` / `build_fingerprint_pipeline_with_mode`）
//! 收到的是宿主直传 `String`，没有 C ABI 那层 `read_utf8` 的 64 KiB 有界扫描兜底
//! ⇒ 一条超长 hex 串换来的是一次与其等长的堆分配，判定却仍落在调用方。
//!
//! 本文件钉的是**契约面**（畸形与超长的输入一律整体拒绝，绝不退化成截断/补齐/
//! 固定种子）；「判定在解码之前」这一条按文本判源码，红能力在
//! `scripts/verify_ffi_input_bounds.py`——行为层面两种写法的返回值本来就没差别，
//! 用返回值判顺序会得到一条恒真的用例（R9-B44 同口径的自证）。
use aegis_policy_core::ffi::{
    build_fingerprint_pipeline, build_fingerprint_pipeline_with_mode, hex_seed_to_bytes,
    FfiProtectionMode,
};

const VALID_SEED: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

#[test]
fn only_an_exactly_sized_hex_seed_is_decoded() {
    assert!(hex_seed_to_bytes(VALID_SEED).is_some());
    assert!(hex_seed_to_bytes("ab").is_none(), "短串整体拒绝");
    assert!(
        hex_seed_to_bytes(&"ab".repeat(33)).is_none(),
        "长串整体拒绝（不截断）"
    );
    // 超长形态：1 MiB / 8 MiB 字符都必须拒到，且**不产生结果**
    for chars in [1_048_576usize, 8_388_608] {
        assert!(
            hex_seed_to_bytes(&"a".repeat(chars)).is_none(),
            "{chars} 字符的输入必须被拒"
        );
    }
}

#[test]
fn host_facing_pipeline_entries_reject_an_oversized_seed() {
    let oversized = "ab".repeat(512 * 1024); // 1 MiB 十六进制字符
    assert_eq!(build_fingerprint_pipeline(oversized.clone()), "");
    assert_eq!(
        build_fingerprint_pipeline_with_mode(
            oversized,
            FfiProtectionMode::Balanced,
            "example.com".into()
        ),
        "",
        "超长种子不得退化成任何注入脚本（RS-036 的 fail-closed 口径）"
    );
    // 反向对照：同一入口对合法种子仍产出脚本，否则上面两条断言可以是恒真
    assert!(!build_fingerprint_pipeline(VALID_SEED.into()).is_empty());
    assert!(!build_fingerprint_pipeline_with_mode(
        VALID_SEED.into(),
        FfiProtectionMode::Balanced,
        "example.com".into()
    )
    .is_empty());
}

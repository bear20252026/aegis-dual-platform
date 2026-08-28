#![no_main]

use libfuzzer_sys::fuzz_target;

// 照搬 warden fuzz 模式：origin parser 应该是 total 的——对任意 UTF-8 输入
// 不 panic、不越界、不溢出、不无限循环。只返回 Option 或内部处理。
// libFuzzer 仍可探索非 UTF-8 字节（credit 不受影响）。
fuzz_target!(|data: &[u8]| {
    if let Ok(url) = std::str::from_utf8(data) {
        let _ = aegis_policy_core::origin::try_parse_external(url);
    }
});

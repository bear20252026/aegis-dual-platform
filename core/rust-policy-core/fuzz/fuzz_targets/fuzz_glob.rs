#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-050：glob_match / glob_subsumes 必须是 total 的——迭代 DP 实现对任意
// 输入不 panic、不栈溢出（递归时代深输入会爆栈）、不无限循环。
// subsumes 全序一致性：a ⊑ b 且 b ⊑ a 则语义等价（此处仅断言 total 性，
// 等价性由单测锁定——fuzz 只找崩溃）。
fuzz_target!(|data: &[u8]| {
    let s = String::from_utf8_lossy(data).into_owned();
    let (pattern, text) = match s.split_once('\n') {
        Some((p, t)) => (p, t),
        None => (s.as_str(), s.as_str()),
    };
    let _ = aegis_policy_core::matcher::glob_match(pattern, text, false);
    let _ = aegis_policy_core::matcher::glob_match(pattern, text, true);
    let _ = aegis_policy_core::matcher::glob_subsumes(pattern, text, false);
    let _ = aegis_policy_core::matcher::glob_subsumes(pattern, text, true);
});

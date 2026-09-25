#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-050：security_policy 面必须 total——sanitize_filename 任意输入输出
// 有界且不 panic；url_decode 拒绝畸形输入只返回 None；scheme 判定纯函数。
fuzz_target!(|data: &[u8]| {
    let s = String::from_utf8_lossy(data);
    let filename = aegis_policy_core::security_policy::SecurityPolicy::sanitize_filename(Some(&s));
    assert!(filename.len() <= s.len() + 32, "清洗后文件名不得膨胀");
    let _ = aegis_policy_core::security_policy::SecurityPolicy::url_decode(&s);
    let _ = aegis_policy_core::security_policy::SecurityPolicy::is_valid_navigation_scheme(Some(&s));
    let _ = aegis_policy_core::security_policy::SecurityPolicy::is_dangerous_external_scheme(Some(&s));
});

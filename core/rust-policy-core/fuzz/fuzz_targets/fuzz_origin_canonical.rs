#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-050：canonicalize_external / try_parse_external 双入口必须 total——
// 与 fuzz_origin 互补：origin 只覆盖 try_parse，canonical（规范化对象
// 构造路径，含尾点剥离/白名单/点段拒绝）此前零 fuzz 覆盖。
fuzz_target!(|data: &[u8]| {
    if let Ok(url) = std::str::from_utf8(data) {
        let _ = aegis_policy_core::origin::canonicalize_external(url);
        let _ = aegis_policy_core::origin::try_parse_external(url);
    }
});

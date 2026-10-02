#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-271（2026-10-01 审计）：Capability::is_origin_allowed 对任意 origin
// 输入必须 total（不 panic、纯判定）；白名单条目亦吃 fuzz 数据（自定义
// 配置面）。配套不变式：空白名单恒拒（fail-closed），"*" 恒放行。
fuzz_target!(|data: &[u8]| {
    let origin = String::from_utf8_lossy(data);
    let entry = origin.clone().into_owned();
    // 空白名单——fail-closed 拒绝
    let empty = aegis_policy_core::capability::Capability::new(
        "fuzz",
        aegis_policy_core::capability::CapabilityScope::Execute,
        vec![],
        None,
    );
    assert!(!empty.is_origin_allowed(&origin));
    // 显式全放行
    let wildcard = aegis_policy_core::capability::Capability::new(
        "fuzz",
        aegis_policy_core::capability::CapabilityScope::Execute,
        vec!["*".into()],
        None,
    );
    assert!(wildcard.is_origin_allowed(&origin));
    // 自定义条目（配置面输入）
    let custom = aegis_policy_core::capability::Capability::new(
        "fuzz",
        aegis_policy_core::capability::CapabilityScope::Execute,
        vec![entry],
        Some(u32::MAX),
    );
    let _ = custom.is_origin_allowed(&origin);
    let _ = custom.is_exhausted();
});

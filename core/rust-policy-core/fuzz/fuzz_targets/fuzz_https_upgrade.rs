#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-271（2026-10-01 审计）：HttpsOnlyState::upgrade 必须是 total 的——
// 任意输入（含超长/畸形/多字节形态）不 panic、不无界分配；产出不变式：
// Some(upgraded) 必以 "https://" 前缀（升级语义），None 表示无需处理。
// 放行判定（allow_http）与计数（MAX_TRACKED_TABS 有界）同面覆盖。
fuzz_target!(|data: &[u8]| {
    let s = String::from_utf8_lossy(data);
    let mut state = aegis_policy_core::https_only::HttpsOnlyState::new();
    if let Some(upgraded) = state.upgrade(&s, "fuzz-tab") {
        assert!(upgraded.starts_with("https://"), "升级产物必须是 https 前缀");
    }
    // 放行/查询/重置路径同面 total
    state.allow_http(&s);
    let _ = state.is_http_allowed(&s);
    state.reset_tab("fuzz-tab");
});

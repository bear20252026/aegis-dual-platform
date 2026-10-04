// —— RS-310（2026-10-02 审计）：C ABI 导出面冻结清单 ——

/// 导出面枚举测试——解析自身源文件（include_str 两文件），提取全部
/// `#[unsafe(no_mangle)]` 导出符号，与冻结 Vec 全等比对。
///
/// 此前导出面无冻结清单：新增 `#[unsafe(no_mangle)]` 符号（有意或
/// 复制粘贴意外）会静默扩大 ABI 契约面（Windows P/Invoke / Android
/// JNA 按符号名绑定，扩面即向后兼容承诺）。现以测试锁定：新增/删除/
/// 改名导出必须显式同步 FROZEN_EXPORTS 清单（清单与源同步是唯一
/// 变更通道，评审时一目了然）。
#[test]
fn c_abi_export_surface_is_frozen() {
    const FROZEN_EXPORTS: &[&str] = &[
        // mod.rs（句柄/生命周期）
        "aegis_policy_core_broker_new",
        "aegis_policy_core_broker_free",
        "aegis_policy_core_string_free",
        // navigation.rs（会话/导航/审批）
        "aegis_policy_core_broker_create_session",
        "aegis_policy_core_broker_destroy_session",
        "aegis_policy_core_broker_advance_document_generation",
        "aegis_policy_core_broker_evaluate_navigation_json",
        "aegis_policy_core_broker_request_navigation_confirmation_json",
        "aegis_policy_core_broker_approve_navigation_confirmation_json",
        "aegis_policy_core_broker_reject_navigation_confirmation",
        "aegis_policy_core_broker_consume_navigation_json",
        // 审计第六轮（2026-10-03/04）：威胁 host 黑名单注入入口——FFI 通路
        // 此前无任何 deny-by-content 接入面（H-7），Android 端因此整体缺黑名单
        "aegis_policy_core_broker_update_host_denylist_json",
    ];
    // 扫描源文件：no_mangle 属性行的下一个 `pub ... fn name(` 行
    // 提取符号名（本 crate 导出全部为该两行形态）
    let mut found: Vec<String> = Vec::new();
    for src in [include_str!("../mod.rs"), include_str!("../navigation.rs")] {
        let mut pending = false;
        for line in src.lines() {
            let t = line.trim();
            if t == "#[unsafe(no_mangle)]" {
                pending = true;
            } else if pending && t.starts_with("pub") && t.contains(" fn ") {
                let name = t
                    .split("fn ")
                    .nth(1)
                    .and_then(|rest| rest.split('(').next())
                    .unwrap_or("<unparseable>")
                    .trim()
                    .to_string();
                found.push(name);
                pending = false;
            }
        }
    }
    found.sort();
    let mut expected: Vec<&str> = FROZEN_EXPORTS.to_vec();
    expected.sort_unstable();
    assert_eq!(
        found, expected,
        "C ABI 导出面与冻结清单不一致——新增/删除/改名导出必须显式更新 \
             FROZEN_EXPORTS（导出面 = ABI 契约，不得静默变更）"
    );
}

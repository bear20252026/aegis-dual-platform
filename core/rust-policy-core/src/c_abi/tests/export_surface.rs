// —— RS-310（2026-10-02 审计）：C ABI 导出面冻结清单 ——

/// 导出面枚举测试——解析自身源文件（include_str 三文件：c_abi 的 mod.rs /
/// navigation.rs 与 crate 根 lib.rs），提取全部 `#[unsafe(no_mangle)]` 导出符号，
/// 与冻结 Vec 全等比对。
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
        // 审计第七轮 R7-RS-02：该入口新增第三参 clear（清空/追加两阶段），
        // 符号名未变 → 冻结面项数不变（参数漂移由 C# 侧 clear 回显探针观测）
        "aegis_policy_core_broker_update_host_denylist_json",
        // lib.rs（ABI 版本探测）——第七轮 R7-RS-04：此前列为 12 项时漏的就是它，
        // Android 真绑定（android/broker/.../NativePolicyCoreGate.kt:118）
        "aegis_policy_core_abi_version",
    ];
    // 扫描源文件：no_mangle 属性行的下一个 `pub ... fn name(` 行
    // 提取符号名（本 crate 导出全部为该两行形态）
    // 审计第七轮 R7-RS-04（2026-10-04）：扫描集此前只有 c_abi 的两文件（12 项），
    // 而 `lib.rs` 的 `aegis_policy_core_abi_version` 是全 crate 第 13 个导出、且被
    // Android 真实绑定（android/broker/.../NativePolicyCoreGate.kt:118）——不在扫描
    // 集即「导出面=契约不得静默变更」只覆盖 12/13，删改名该符号门禁全绿。
    // 口径：按属性标记计数（新增 no_mangle 文件只要被纳入扫描集即自动入面），
    // 扫描集清单与 FROZEN_EXPORTS 由本用例逐符号全等比对兜住。
    let mut found: Vec<String> = Vec::new();
    for src in [
        include_str!("../mod.rs"),
        include_str!("../navigation.rs"),
        include_str!("../../lib.rs"),
    ] {
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

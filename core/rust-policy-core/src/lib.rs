//! Aegis 纯策略核心（蓝图阶段 F——Rust 试点）。
//!
//! 约束（蓝图 core/）：确定性、无副作用——输入相同 Decision 必须相同；
//! 无文件/网络/环境变量/标签/UI 访问（除参数注入）；平台只能依赖 core，
//! 不能反向依赖。
//!
//! 试点范围（蓝图阶段 F 第一推荐项）：update manifest canonicalization +
//! Ed25519 阈值验证；第二项：URL/Origin canonicalization。
//! 与 C#/Kotlin reference + contracts/vectors 差分一致（跨语言测试向量）。

pub mod action_policy;
pub mod adblock;
pub mod bridge_guard;
pub mod broker;
pub mod c_abi;
pub mod capability;
pub mod command_bar;
pub mod decision;
pub mod executor;
pub mod ext_proxy;
pub mod ffi;
pub mod font_norm;
pub mod https_only;
pub mod js_inject;
pub mod letterbox;
pub mod matcher;
pub mod oracle;
pub mod origin;
pub mod per_site_seed;
pub mod policy;
pub mod protection_mode;
pub mod query_strip;
pub mod security_policy;
pub mod session_state;
pub mod shield;
pub mod space_routing;
pub mod timer_prec;
pub mod tostring_guard;
pub mod update_manifest;
pub mod util;
pub mod webgl_spoof;

// UniFFI 官方要求（proc-macro 模式）：crate 根调用 setup_scaffolding!()
uniffi::setup_scaffolding!();

/// 稳定 C ABI 的兼容版本；Windows P/Invoke 包装器在调用策略接口前必须验证它。
pub const POLICY_CORE_ABI_VERSION: u32 = 1;

/// 供受管理平台探测动态库兼容性的无状态、无分配 C ABI 入口。
///
/// 此入口不处理策略决策；它仅用于在加载期将库名和 ABI 版本绑定到宿主预期值。
#[no_mangle]
pub extern "C" fn aegis_policy_core_abi_version() -> u32 {
    POLICY_CORE_ABI_VERSION
}

#[cfg(test)]
mod native_abi_tests {
    use super::*;

    #[test]
    fn c_abi_version_is_stable() {
        assert_eq!(aegis_policy_core_abi_version(), POLICY_CORE_ABI_VERSION);
        assert_eq!(POLICY_CORE_ABI_VERSION, 1);
    }
}

/// 指纹防护注入管线（管道化组合所有防护阶段）。
///
/// 每个阶段独立、可拆卸、可组合——移除/新增阶段不影响其他阶段。
/// 管线顺序：ToStringGuard → PerSiteSeed → FingerprintShield → LetterboxShield → QueryStripper → FontNormalizer → WebGLSpoof → TimerPrecision → ExtProxy
///
/// # 用法
/// ```rust
/// use aegis_policy_core::fingerprint_pipeline;
/// let shield = aegis_policy_core::shield::FingerprintShield::new();
/// let script = fingerprint_pipeline(&shield);
/// ```
pub fn fingerprint_pipeline(shield: &shield::FingerprintShield) -> String {
    let session_hex = shield.seed_hex();
    let tostring_guard = tostring_guard::ToStringGuard::new();
    let per_site = per_site_seed::PerSiteSeed::new(shield.seed_bytes());
    let letterbox = letterbox::LetterboxShield::new();
    let query_strip = query_strip::QueryStripper::new();
    let font_norm = font_norm::FontNormalizer::new();
    let webgl_spoof = webgl_spoof::WebGLSpoof::new();
    let timer_prec = timer_prec::TimerPrecision::new();
    let ext_proxy = ext_proxy::ExtProxy::new();
    format!(
        "{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}",
        tostring_guard.inject_script(),
        per_site.inject_script(&session_hex),
        shield.inject_script(),
        letterbox.inject_script(),
        query_strip.inject_script(),
        font_norm.inject_script(),
        webgl_spoof.inject_script(),
        timer_prec.inject_script(),
        ext_proxy.inject_script()
    )
}

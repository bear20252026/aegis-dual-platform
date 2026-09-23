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

/// C ABI v3：新增 Rust 托管的确认登记、批准兑换与拒绝接口。
/// Windows/Android 宿主在调用策略接口前必须验证该版本，旧宿主应失败闭合。
pub const POLICY_CORE_ABI_VERSION: u32 = 3;

/// 供受管理平台探测动态库兼容性的无状态、无分配 C ABI 入口。
///
/// 此入口不处理策略决策；它仅用于在加载期将库名和 ABI 版本绑定到宿主预期值。
#[no_mangle]
pub extern "C" fn aegis_policy_core_abi_version() -> u32 {
    POLICY_CORE_ABI_VERSION
}

/// 指纹防护注入管线（管道化组合所有防护阶段）。
///
/// 每个阶段独立、可拆卸、可组合——移除/新增阶段不影响其他阶段。
/// 管线顺序：ToStringGuard → PerSiteSeed → FingerprintShield → LetterboxShield → QueryStripper → FontNormalizer → WebGLSpoof → TimerPrecision → ExtProxy
///
/// `domain`：该 WebView 顶层文档的 eTLD+1 域名（宿主已知），供 PerSiteSeed
/// 按域派生站点种子——此前管线把会话种子 hex 当域名传参，所有站点共用
/// 同一种子，per-site 隔离完全失效。
///
/// # 用法
/// ```rust
/// use aegis_policy_core::fingerprint_pipeline;
/// let shield = aegis_policy_core::shield::FingerprintShield::new();
/// let script = fingerprint_pipeline(&shield, "example.com");
/// ```
pub fn fingerprint_pipeline(shield: &shield::FingerprintShield, domain: &str) -> String {
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
        per_site.inject_script(domain),
        shield.inject_script(),
        letterbox.inject_script(),
        query_strip.inject_script(),
        font_norm.inject_script(),
        webgl_spoof.inject_script(),
        timer_prec.inject_script(),
        ext_proxy.inject_script()
    )
}

#[cfg(test)]
mod native_abi_tests {
    use super::*;

    #[test]
    fn c_abi_version_is_stable() {
        assert_eq!(aegis_policy_core_abi_version(), POLICY_CORE_ABI_VERSION);
        assert_eq!(POLICY_CORE_ABI_VERSION, 3);
    }

    #[test]
    fn pipeline_per_site_seed_varies_by_domain() {
        // RS-002 回归：管线必须把真实域名传给 PerSiteSeed——
        // 此前误传会话种子 hex 当域名，所有站点注入相同种子。
        let shield = shield::FingerprintShield::new();
        let a = fingerprint_pipeline(&shield, "example.com");
        let b = fingerprint_pipeline(&shield, "tracker.example.net");
        let seed_of = |s: &str| {
            s.lines()
                .find(|l| l.contains("__AEGIS_SITE_SEED"))
                .unwrap()
                .to_string()
        };
        assert_ne!(seed_of(&a), seed_of(&b));
        // 同域确定性
        assert_eq!(
            seed_of(&a),
            seed_of(&fingerprint_pipeline(&shield, "example.com"))
        );
        // 站点种子不得等于会话种子 hex（域名错传的特征）
        assert!(!seed_of(&a).contains(&shield.seed_hex()));
    }

    #[test]
    fn mode_pipeline_per_site_seed_varies_by_domain() {
        use crate::protection_mode::{fingerprint_pipeline_with_mode, ProtectionMode};
        let shield = shield::FingerprintShield::new();
        let a = fingerprint_pipeline_with_mode(&shield, ProtectionMode::Balanced, "a.com");
        let b = fingerprint_pipeline_with_mode(&shield, ProtectionMode::Balanced, "b.com");
        let seed_of = |s: &str| {
            s.lines()
                .find(|l| l.contains("__AEGIS_SITE_SEED"))
                .unwrap()
                .to_string()
        };
        assert_ne!(seed_of(&a), seed_of(&b));
    }
}

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
pub mod capability;
pub mod decision;
pub mod executor;
pub mod https_only;
pub mod letterbox;
pub mod matcher;
pub mod oracle;
pub mod origin;
pub mod per_site_seed;
pub mod policy;
pub mod query_strip;
pub mod security_policy;
pub mod session_state;
pub mod shield;
pub mod update_manifest;

/// 指纹防护注入管线（管道化组合所有防护阶段）。
///
/// 每个阶段独立、可拆卸、可组合——移除/新增阶段不影响其他阶段。
/// 管线顺序：PerSiteSeed → FingerprintShield → LetterboxShield → QueryStripper
///
/// # 用法
/// ```rust
/// use aegis_policy_core::fingerprint_pipeline;
/// let shield = aegis_policy_core::shield::FingerprintShield::new();
/// let script = fingerprint_pipeline(&shield);
/// // script 包含 per-site 种子 + Canvas/WebGL/Audio 噪声 + Letterboxing + 查询剥离
/// ```
pub fn fingerprint_pipeline(shield: &shield::FingerprintShield) -> String {
    let session_hex = shield.seed_hex();
    let per_site = per_site_seed::PerSiteSeed::new(shield.seed_bytes());
    let letterbox = letterbox::LetterboxShield::new();
    let query_strip = query_strip::QueryStripper::new();
    format!(
        "{}\n{}\n{}\n{}",
        per_site.inject_script(&session_hex),
        shield.inject_script(),
        letterbox.inject_script(),
        query_strip.inject_script()
    )
}

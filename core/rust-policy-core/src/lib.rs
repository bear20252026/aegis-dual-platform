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
pub mod matcher;
pub mod oracle;
pub mod origin;
pub mod policy;
pub mod security_policy;
pub mod session_state;
pub mod shield;
pub mod update_manifest;

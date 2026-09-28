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
#[unsafe(no_mangle)]
pub extern "C" fn aegis_policy_core_abi_version() -> u32 {
    POLICY_CORE_ABI_VERSION
}

/// 指纹防护注入管线（管道化组合所有防护阶段）。
///
/// 每个阶段独立、可拆卸、可组合——移除/新增阶段不影响其他阶段。
/// 管线顺序：ProtectionMode 声明头 → ToStringGuard → PerSiteSeed →
/// FingerprintShield → LetterboxShield → QueryStripper → FontNormalizer →
/// WebGLSpoof → TimerPrecision → ExtProxy
///
/// `domain`：该 WebView 顶层文档的 eTLD+1 域名（宿主已知），供 PerSiteSeed
/// 按域派生站点种子——此前管线把会话种子 hex 当域名传参，所有站点共用
/// 同一种子，per-site 隔离完全失效。
///
/// RS-233（2026-09-26 审计）：单源组装——此前本入口用 JsPipeline trait
/// 对象手写九阶段清单，protection_mode::fingerprint_pipeline_with_mode
/// 用 parts Vec + enable_* 分支另写一份，阶段清单/顺序两处维护（增删
/// 阶段漏改一侧即两端口径分裂）。现委托
/// `fingerprint_pipeline_with_mode(Maximum, domain)`（Maximum = 全九阶段
/// 启用；输出额外携带模式声明头——Maximum 模式声明，语义等价）。
///
/// # 用法
/// ```rust
/// use aegis_policy_core::fingerprint_pipeline;
/// let shield = aegis_policy_core::shield::FingerprintShield::new();
/// let script = fingerprint_pipeline(&shield, "example.com");
/// ```
pub fn fingerprint_pipeline(shield: &shield::FingerprintShield, domain: &str) -> String {
    protection_mode::fingerprint_pipeline_with_mode(
        shield,
        protection_mode::ProtectionMode::Maximum,
        domain,
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

    #[test]
    fn pipeline_stage_names_trace_all_nine_modules() {
        // RS-040 回归（阶段覆盖面）：管线输出必须覆盖全部 9 阶段。
        // RS-233（2026-09-26 审计）：组装已单源化——本入口委托
        // fingerprint_pipeline_with_mode(Maximum)（此前 JsPipeline 与
        // parts Vec 两套手写清单），阶段清单漂移在 protection_mode 侧
        // 的逐模式测试与本测试双重锁定
        let shield = shield::FingerprintShield::new();
        let script = fingerprint_pipeline(&shield, "example.com");
        for name in [
            "ToStringGuard",
            "PerSiteSeed",
            "FingerprintShield",
            "LetterboxShield",
            "QueryStripper",
            "FontNormalizer",
            "WebGLSpoof",
            "TimerPrecision",
            "ExtProxy",
        ] {
            // 阶段名以模块头注释形态出现于脚本
            assert!(script.contains(name), "管线缺少阶段 {name}");
        }
    }

    #[test]
    fn pipeline_webgl_spoofed_once_single_owner() {
        // RS-026 回归：WebGL vendor/renderer 伪装单一负责——shield 的矛盾
        // 块已移除，getParameter 覆盖仅存在于 webgl_spoof 阶段
        let shield = shield::FingerprintShield::new();
        let script = fingerprint_pipeline(&shield, "example.com");
        assert!(
            script.contains("UNMASKED_VENDOR_WEBGL"),
            "webgl_spoof 覆盖保留"
        );
        assert!(
            !shield.inject_script().contains("getParameter"),
            "shield 不得再覆盖 WebGL getParameter（口径矛盾）"
        );
    }

    // —— RS-051/052 回归（审计 2026-09-25） ——

    #[test]
    fn pipeline_output_fully_deterministic() {
        // RS-051：同一 (shield, domain) 两次构建必须逐字节一致——蓝图
        // core 确定性约束约束的是整脚本（全部阶段与常量），不只 seed 行
        let shield = shield::FingerprintShield::new();
        let a = fingerprint_pipeline(&shield, "example.com");
        let b = fingerprint_pipeline(&shield, "example.com");
        assert_eq!(a, b);
        assert_eq!(
            fingerprint_pipeline(&shield, "other.net"),
            fingerprint_pipeline(&shield, "other.net")
        );
    }

    #[test]
    fn pipeline_stages_appear_in_declared_order() {
        // RS-051：九阶段在脚本中按声明顺序出现——顺序错位会改变注入
        // 优先级（如 QueryStripper 必须先于其消费方阶段执行）
        let shield = shield::FingerprintShield::new();
        let script = fingerprint_pipeline(&shield, "example.com");
        let names = [
            "ToStringGuard",
            "PerSiteSeed",
            "FingerprintShield",
            "LetterboxShield",
            "QueryStripper",
            "FontNormalizer",
            "WebGLSpoof",
            "TimerPrecision",
            "ExtProxy",
        ];
        let mut cursor = 0;
        for name in names {
            let pos = script[cursor..]
                .find(name)
                .unwrap_or_else(|| panic!("阶段 {name} 缺失或顺序错位"));
            cursor += pos + name.len();
        }
    }

    #[test]
    fn abi_version_probe_idempotent_failclosed_contract() {
        // RS-052：ABI 探测入口幂等无副作用——宿主加载期可重复探测；
        // 门禁契约：POLICY_CORE_ABI_VERSION 变更即破坏性事件，旧宿主
        // 比对不一致时必须拒绝加载（fail-closed）。本测试锁定版本常量
        // 与入口返回严格相等，任何漂移在测试期即失败。
        assert_eq!(aegis_policy_core_abi_version(), POLICY_CORE_ABI_VERSION);
        assert_eq!(
            aegis_policy_core_abi_version(),
            aegis_policy_core_abi_version(),
            "探测入口幂等（重复调用同值）"
        );
    }

    // —— RS-233 回归（审计 2026-09-26） ——

    #[test]
    fn fingerprint_pipeline_delegates_to_maximum_mode_single_source() {
        // RS-233：九阶段管线单源组装——本入口必须逐字节等于
        // fingerprint_pipeline_with_mode(Maximum, domain)。此前两套手写
        // 清单（JsPipeline trait 对象 vs parts Vec），阶段增删漏改一侧
        // 即两端口径分裂；本断言让任何一侧私改立刻红灯
        use crate::protection_mode::{fingerprint_pipeline_with_mode, ProtectionMode};
        let shield = shield::FingerprintShield::new();
        for domain in ["example.com", "other.net"] {
            assert_eq!(
                fingerprint_pipeline(&shield, domain),
                fingerprint_pipeline_with_mode(&shield, ProtectionMode::Maximum, domain),
                "fingerprint_pipeline 必须委托 Maximum 模式单源组装（{domain}）"
            );
        }
    }
}

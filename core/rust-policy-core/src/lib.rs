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
    // RS-040（审计 2026-09-24）：管线改用 JsPipeline trait 对象组装——
    // 此前 JsInjectable 抽象与实现脱节（9 模块零实现，直调 inherent 方法）。
    // 顺序保持不变：ToStringGuard → PerSiteSeed → FingerprintShield →
    // LetterboxShield → QueryStripper → FontNormalizer → WebGLSpoof →
    // TimerPrecision → ExtProxy
    // PerSiteStage 持有种子与域名的所有权（JsPipeline 要求 'static）
    struct PerSiteStage {
        seed: per_site_seed::PerSiteSeed,
        domain: String,
    }
    impl js_inject::JsInjectable for PerSiteStage {
        fn name(&self) -> &str {
            "PerSiteSeed"
        }
        fn inject_script(&self) -> String {
            self.seed.inject_script(&self.domain)
        }
    }

    let per_site = per_site_seed::PerSiteSeed::new(shield.seed_bytes());
    let mut pipeline = js_inject::JsPipeline::new();
    pipeline.add(Box::new(tostring_guard::ToStringGuard::new()));
    pipeline.add(Box::new(PerSiteStage {
        seed: per_site,
        domain: domain.to_string(),
    }));
    // shield 借用不适配 'static 管线——Clone（32 字节种子拷贝，代价可忽略）
    pipeline.add(Box::new(shield.clone()));
    pipeline.add(Box::new(letterbox::LetterboxShield::new()));
    pipeline.add(Box::new(query_strip::QueryStripper::new()));
    pipeline.add(Box::new(font_norm::FontNormalizer::new()));
    pipeline.add(Box::new(webgl_spoof::WebGLSpoof::new()));
    pipeline.add(Box::new(timer_prec::TimerPrecision::new()));
    pipeline.add(Box::new(ext_proxy::ExtProxy::new()));
    pipeline.build()
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
        use crate::protection_mode::{ProtectionMode, fingerprint_pipeline_with_mode};
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
        // RS-040 回归：管线必须经 JsInjectable trait 对象组装，且阶段名
        // 覆盖全部 9 模块（含 PerSiteStage 适配器）
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
}

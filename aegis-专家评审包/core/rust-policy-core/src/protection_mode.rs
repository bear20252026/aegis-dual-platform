// 由账号2生成
//! ProtectionMode（参照 fingerprint-toolkit 三种保护模式）。
//!
//! 用户可切换防护等级：兼容 / 平衡 / 最大隐私。
//! 每种模式控制哪些管道阶段激活，平衡隐私与可用性。
//!
//! 原始版权声明：
//!   fingerprint-toolkit by xuweizhengo
//!   https://github.com/xuweizhengo/fingerprint-toolkit
//!
//! 模式设计：
//!   - Compatible（兼容）：最小防护，仅 Canvas 噪声——网站兼容性最好
//!   - Balanced（平衡）：默认模式，大部分防护启用——隐私与可用性平衡
//!   - Maximum（最大隐私）：全部 9 阶段启用，最激进设置
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：与 fingerprint_pipeline 独立组合。

use std::fmt;

/// 保护模式枚举。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProtectionMode {
    /// 兼容模式——最小防护，网站兼容性最好。
    Compatible,
    /// 平衡模式——默认，大部分防护启用。
    Balanced,
    /// 最大隐私模式——全部防护启用，最激进。
    Maximum,
}

impl ProtectionMode {
    /// 从字符串解析保护模式。
    pub fn parse(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "compatible" | "compat" | "0" => Some(Self::Compatible),
            "balanced" | "balance" | "1" => Some(Self::Balanced),
            "maximum" | "max" | "2" => Some(Self::Maximum),
            _ => None,
        }
    }

    /// 模式名称。
    pub fn name(&self) -> &'static str {
        match self {
            Self::Compatible => "compatible",
            Self::Balanced => "balanced",
            Self::Maximum => "maximum",
        }
    }

    /// 模式描述。
    pub fn description(&self) -> &'static str {
        match self {
            Self::Compatible => "最小防护——仅 Canvas 噪声，网站兼容性最好",
            Self::Balanced => "平衡模式——大部分防护启用，隐私与可用性平衡",
            Self::Maximum => "最大隐私——全部 9 阶段启用，最激进设置",
        }
    }

    /// 是否启用 ToStringGuard（Stage 1）。
    pub fn enable_tostring_guard(&self) -> bool {
        matches!(self, Self::Balanced | Self::Maximum)
    }

    /// 是否启用 PerSiteSeed（Stage 2）。
    pub fn enable_per_site_seed(&self) -> bool {
        matches!(self, Self::Balanced | Self::Maximum)
    }

    /// 是否启用 Canvas/WebGL/Audio 噪声（Stage 3）。
    /// 所有模式都启用——这是最基本的防护。
    pub fn enable_fingerprint_shield(&self) -> bool {
        true
    }

    /// 是否启用 LetterboxShield（Stage 4）。
    pub fn enable_letterbox(&self) -> bool {
        matches!(self, Self::Maximum)
    }

    /// 是否启用 QueryStripper（Stage 5）。
    pub fn enable_query_strip(&self) -> bool {
        matches!(self, Self::Balanced | Self::Maximum)
    }

    /// 是否启用 FontNormalizer（Stage 6）。
    pub fn enable_font_normalizer(&self) -> bool {
        matches!(self, Self::Maximum)
    }

    /// 是否启用 WebGLSpoof（Stage 7）。
    pub fn enable_webgl_spoof(&self) -> bool {
        matches!(self, Self::Balanced | Self::Maximum)
    }

    /// 是否启用 TimerPrecision（Stage 8）。
    pub fn enable_timer_precision(&self) -> bool {
        matches!(self, Self::Maximum)
    }

    /// 是否启用 ExtProxy（Stage 9）。
    pub fn enable_ext_proxy(&self) -> bool {
        matches!(self, Self::Maximum)
    }

    /// 生成模式切换 JS 注入脚本。
    ///
    /// 设置 `__AEGIS_PROTECTION_MODE` 全局常量，
    /// 供其他模块查询当前模式。
    pub fn inject_script(&self) -> String {
        let mode = self.name();
        let desc = self.description();
        format!(
            r#"
// Aegis ProtectionMode — 防护模式切换
// 模式：{mode} — {desc}
Object.defineProperty(window, '__AEGIS_PROTECTION_MODE', {{
  value: '{mode}',
  writable: false,
  configurable: false
}});
"#
        )
    }
}

impl fmt::Display for ProtectionMode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.name())
    }
}

/// 模式感知的指纹防护管线。
///
/// 根据 ProtectionMode 选择性激活管道阶段，
/// 返回组合后的 JS 注入脚本。
pub fn fingerprint_pipeline_with_mode(
    shield: &crate::shield::FingerprintShield,
    mode: ProtectionMode,
) -> String {
    let mut parts: Vec<String> = Vec::new();

    // Stage 0: 模式声明
    parts.push(mode.inject_script());

    // Stage 1: ToStringGuard
    if mode.enable_tostring_guard() {
        parts.push(crate::tostring_guard::ToStringGuard::new().inject_script());
    }

    // Stage 2: PerSiteSeed
    if mode.enable_per_site_seed() {
        let session_hex = shield.seed_hex();
        parts.push(
            crate::per_site_seed::PerSiteSeed::new(shield.seed_bytes()).inject_script(&session_hex),
        );
    }

    // Stage 3: Canvas/WebGL/Audio 噪声（所有模式启用）
    if mode.enable_fingerprint_shield() {
        parts.push(shield.inject_script());
    }

    // Stage 4: LetterboxShield
    if mode.enable_letterbox() {
        parts.push(crate::letterbox::LetterboxShield::new().inject_script());
    }

    // Stage 5: QueryStripper
    if mode.enable_query_strip() {
        parts.push(crate::query_strip::QueryStripper::new().inject_script());
    }

    // Stage 6: FontNormalizer
    if mode.enable_font_normalizer() {
        parts.push(crate::font_norm::FontNormalizer::new().inject_script());
    }

    // Stage 7: WebGLSpoof
    if mode.enable_webgl_spoof() {
        parts.push(crate::webgl_spoof::WebGLSpoof::new().inject_script());
    }

    // Stage 8: TimerPrecision
    if mode.enable_timer_precision() {
        parts.push(crate::timer_prec::TimerPrecision::new().inject_script());
    }

    // Stage 9: ExtProxy
    if mode.enable_ext_proxy() {
        parts.push(crate::ext_proxy::ExtProxy::new().inject_script());
    }

    parts.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compatible_mode_minimal() {
        let m = ProtectionMode::Compatible;
        assert!(m.enable_fingerprint_shield()); // Stage 3 始终启用
        assert!(!m.enable_letterbox());
        assert!(!m.enable_font_normalizer());
        assert!(!m.enable_timer_precision());
        assert!(!m.enable_ext_proxy());
    }

    #[test]
    fn balanced_mode_default() {
        let m = ProtectionMode::Balanced;
        assert!(m.enable_fingerprint_shield());
        assert!(m.enable_per_site_seed());
        assert!(m.enable_query_strip());
        assert!(m.enable_webgl_spoof());
        assert!(!m.enable_letterbox());
        assert!(!m.enable_ext_proxy());
    }

    #[test]
    fn maximum_mode_all_enabled() {
        let m = ProtectionMode::Maximum;
        assert!(m.enable_tostring_guard());
        assert!(m.enable_per_site_seed());
        assert!(m.enable_fingerprint_shield());
        assert!(m.enable_letterbox());
        assert!(m.enable_query_strip());
        assert!(m.enable_font_normalizer());
        assert!(m.enable_webgl_spoof());
        assert!(m.enable_timer_precision());
        assert!(m.enable_ext_proxy());
    }

    #[test]
    fn parse_parses_all_modes() {
        assert_eq!(
            ProtectionMode::parse("compatible"),
            Some(ProtectionMode::Compatible)
        );
        assert_eq!(
            ProtectionMode::parse("balanced"),
            Some(ProtectionMode::Balanced)
        );
        assert_eq!(
            ProtectionMode::parse("maximum"),
            Some(ProtectionMode::Maximum)
        );
        assert_eq!(ProtectionMode::parse("MAX"), Some(ProtectionMode::Maximum));
        assert_eq!(ProtectionMode::parse("unknown"), None);
    }

    #[test]
    fn script_contains_mode_name() {
        let m = ProtectionMode::Balanced;
        let script = m.inject_script();
        assert!(script.contains("balanced"));
        assert!(script.contains("__AEGIS_PROTECTION_MODE"));
    }

    #[test]
    fn mode_display() {
        assert_eq!(ProtectionMode::Compatible.to_string(), "compatible");
        assert_eq!(ProtectionMode::Maximum.to_string(), "maximum");
    }
}

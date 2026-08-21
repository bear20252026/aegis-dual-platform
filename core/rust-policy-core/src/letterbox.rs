// 由账号2生成
//! LetterboxShield（参照 Mullvad Browser / Tor Browser letterboxing 策略）。
//!
//! 将屏幕/窗口尺寸圆整到固定网格（默认 200×100px），
//! 使所有用户落入有限的"桶"中，防止基于屏幕尺寸的指纹识别。
//!
//! 原始版权声明：
//!   Tor Browser letterboxing implementation by The Tor Project
//!   Licensed under MPL-2.0
//!   https://gitlab.torproject.org/tpo/applications/tor-browser
//!
//!   Mullvad Browser fingerprinting resistance by Mullvad VPN
//!   Licensed under MPL-2.0
//!   https://github.com/mullvad/browser
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：与 FingerprintShield 等管道阶段独立组合注入。

use std::fmt;

/// Letterboxing 网格配置。
///
/// 窗口尺寸将被圆整到 `width_step` × `height_step` 的倍数。
/// 默认 200×100（与 Tor/Mullvad 一致）。
#[derive(Debug, Clone)]
pub struct LetterboxConfig {
    /// 宽度圆整步长（像素）。
    pub width_step: u32,
    /// 高度圆整步长（像素）。
    pub height_step: u32,
    /// 最小窗口宽度（像素）。
    pub min_width: u32,
    /// 最小窗口高度（像素）。
    pub min_height: u32,
}

impl Default for LetterboxConfig {
    fn default() -> Self {
        Self {
            width_step: 200,
            height_step: 100,
            min_width: 200,
            min_height: 100,
        }
    }
}

/// LetterboxShield — 屏幕/窗口尺寸圆整防护。
///
/// 生成 JS 脚本，覆盖 `screen.width/height` 和 `window.innerWidth/Height`，
/// 使返回值圆整到配置的网格倍数。
///
/// 参照 Mullvad Browser `privacy.resistFingerprinting` 的 letterboxing 实现：
/// - 窗口尺寸圆整到 200×100px 网格
/// - 所有用户落入有限桶中，防止单一化指纹
/// - 内容区域用 CSS padding 填充到实际窗口尺寸
pub struct LetterboxShield {
    config: LetterboxConfig,
}

impl fmt::Debug for LetterboxShield {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "LetterboxShield({}×{})",
            self.config.width_step, self.config.height_step
        )
    }
}

impl LetterboxShield {
    /// 用默认配置创建（200×100 网格）。
    pub fn new() -> Self {
        Self {
            config: LetterboxConfig::default(),
        }
    }

    /// 用自定义配置创建。
    pub fn with_config(config: LetterboxConfig) -> Self {
        Self { config }
    }

    /// 生成 Letterboxing JS 注入脚本。
    ///
    /// 覆盖以下 API 使返回值圆整：
    /// - `screen.width` / `screen.height`
    /// - `screen.availWidth` / `screen.availHeight`
    /// - `window.innerWidth` / `window.innerHeight`
    /// - `window.outerWidth` / `window.outerHeight`
    ///
    /// 原始实现参照 Tor Browser 的
    /// `dom/base/nsScreen.cpp::MaybeRoundedScreenRect()` 和
    /// `nsGlobalWindowOuter::GetInnerHeight()`。
    pub fn inject_script(&self) -> String {
        let ws = self.config.width_step;
        let hs = self.config.height_step;
        let min_w = self.config.min_width;
        let min_h = self.config.min_height;
        format!(
            r#"
// Aegis LetterboxShield — 屏幕/窗口尺寸圆整（参照 Mullvad/Tor Browser）
// 原始实现：Tor Project (MPL-2.0) / Mullvad VPN (MPL-2.0)
// 策略：将尺寸圆整到 {ws}×{hs}px 网格，使所有用户落入有限"桶"中
(function() {{
  var WS = {ws}, HS = {hs}, MW = {min_w}, MH = {min_h};
  function roundTo(v, step, minV) {{
    return Math.max(minV, Math.round(v / step) * step);
  }}

  // 覆盖 screen 属性
  try {{
    var osW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'width');
    var osH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'height');
    var osAW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availWidth');
    var osAH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availHeight');
    if (osW) Object.defineProperty(screen, 'width', {{ get: function() {{ return roundTo(osW.get.call(this), WS, MW); }} }});
    if (osH) Object.defineProperty(screen, 'height', {{ get: function() {{ return roundTo(osH.get.call(this), HS, MH); }} }});
    if (osAW) Object.defineProperty(screen, 'availWidth', {{ get: function() {{ return roundTo(osAW.get.call(this), WS, MW); }} }});
    if (osAH) Object.defineProperty(screen, 'availHeight', {{ get: function() {{ return roundTo(osAH.get.call(this), HS, MH); }} }});
  }} catch(e) {{}}

  // 覆盖 window 尺寸属性
  try {{
    Object.defineProperty(window, 'innerWidth', {{ get: function() {{ return roundTo(window.innerWidth, WS, MW); }} }});
    Object.defineProperty(window, 'innerHeight', {{ get: function() {{ return roundTo(window.innerHeight, HS, MH); }} }});
    Object.defineProperty(window, 'outerWidth', {{ get: function() {{ return roundTo(window.outerWidth, WS, MW); }} }});
    Object.defineProperty(window, 'outerHeight', {{ get: function() {{ return roundTo(window.outerHeight, HS, MH); }} }});
  }} catch(e) {{}}
}})();
"#
        )
    }
}

impl Default for LetterboxShield {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_is_200x100() {
        let config = LetterboxConfig::default();
        assert_eq!(config.width_step, 200);
        assert_eq!(config.height_step, 100);
    }

    #[test]
    fn script_contains_rounding_logic() {
        let shield = LetterboxShield::new();
        let script = shield.inject_script();
        assert!(script.contains("roundTo"));
        assert!(script.contains("200"));
        assert!(script.contains("100"));
        assert!(script.contains("Screen.prototype"));
        assert!(script.contains("innerWidth"));
    }

    #[test]
    fn custom_config_reflected_in_script() {
        let config = LetterboxConfig {
            width_step: 100,
            height_step: 50,
            min_width: 100,
            min_height: 50,
        };
        let shield = LetterboxShield::with_config(config);
        let script = shield.inject_script();
        assert!(script.contains("100"));
        assert!(script.contains("50"));
    }

    #[test]
    fn debug_format_shows_dimensions() {
        let shield = LetterboxShield::new();
        let debug = format!("{:?}", shield);
        assert!(debug.contains("200"));
        assert!(debug.contains("100"));
    }
}

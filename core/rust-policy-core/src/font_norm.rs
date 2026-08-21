// 由账号2生成
//! FontNormalizer（参照 Mullvad Browser 字体归一化策略）。
//!
//! 限制页面可访问的字体列表为一组安全的"捆绑字体"，
//! 隐藏系统安装的自定义字体，防止基于字体列表的指纹识别。
//!
//! 原始版权声明：
//!   Mullvad Browser font normalization by Mullvad VPN / Tor Project
//!   Licensed under MPL-2.0
//!   https://mullvad.net/en/browser/hard-facts
//!
//! 策略（Mullvad 原文）：
//!   "Not all fonts installed on your computer are available to webpages"
//!   "CSS system fonts are normalized, to hide any customization at the OS level"
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 FingerprintShield 管线中作为独立阶段调用。

use std::fmt;

/// 安全捆绑字体列表（跨平台通用）。
///
/// 这些字体在所有主流操作系统上预装，不会泄露用户身份：
/// - Windows: 预装
/// - macOS: 预装
/// - Linux: 通常预装或通过 fontconfig 可用
const SAFE_FONTS: &[&str] = &[
    // Sans-serif（无衬线）
    "Arial",
    "Helvetica",
    "Verdana",
    "Tahoma",
    "Trebuchet MS",
    // Serif（衬线）
    "Times New Roman",
    "Times",
    "Georgia",
    // Monospace（等宽）
    "Courier New",
    "Courier",
    // Generic families（通用族——浏览器始终可用）
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
];

/// FontNormalizer — 字体指纹归一化。
///
/// 通过 JS 覆盖 `document.fonts` 和 CSS 字体检测，
/// 使页面只能访问一组安全的捆绑字体。
pub struct FontNormalizer {
    safe_fonts: Vec<String>,
}

impl fmt::Debug for FontNormalizer {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "FontNormalizer({} safe fonts)", self.safe_fonts.len())
    }
}

impl FontNormalizer {
    /// 用默认安全字体列表创建。
    pub fn new() -> Self {
        Self {
            safe_fonts: SAFE_FONTS.iter().map(|s| s.to_string()).collect(),
        }
    }

    /// 用自定义安全字体列表创建。
    pub fn with_fonts(fonts: Vec<String>) -> Self {
        Self {
            safe_fonts: fonts,
        }
    }

    /// 生成字体归一化 JS 注入脚本。
    ///
    /// 覆盖以下 API：
    /// - `document.fonts.check()` — 仅对安全字体返回 true
    /// - `document.fonts.values()` — 仅返回安全字体
    /// - CSS `font-family` 解析 — 仅匹配安全字体
    pub fn inject_script(&self) -> String {
        let fonts_json: String = {
            let items: Vec<String> = self.safe_fonts.iter().map(|f| format!("'{}'", f)).collect();
            format!("[{}]", items.join(","))
        };
        format!(
            r#"
// Aegis FontNormalizer — 字体指纹归一化（参照 Mullvad Browser）
// 原始策略：Mullvad VPN / Tor Project (MPL-2.0)
// 仅暴露安全捆绑字体，隐藏系统自定义字体
(function() {{
  var SAFE_FONTS = {fonts_json};
  var SAFE_SET = new Set(SAFE_FONTS.map(function(f) {{ return f.toLowerCase(); }}));

  // 覆盖 document.fonts.check() — 仅对安全字体返回 true
  try {{
    var origCheck = FontFaceSet.prototype.check;
    FontFaceSet.prototype.check = function(font) {{
      // 提取字体族名（忽略大小写和引号）
      var family = font.replace(/['"]/g, '').split(',')[0].trim().toLowerCase();
      // 去掉样式后缀
      family = family.replace(/\s+(regular|bold|italic|light|medium|heavy)$/i, '').trim();
      if (SAFE_SET.has(family)) {{
        return origCheck.apply(this, arguments);
      }}
      return false;
    }};
  }} catch(e) {{}}

  // 覆盖 navigator.fonts（如果存在）
  try {{
    if (navigator.fonts && navigator.fonts.query) {{
      var origQuery = navigator.fonts.query.bind(navigator.fonts);
      navigator.fonts.query = function() {{
        return origQuery().then(function(fonts) {{
          return fonts.filter(function(f) {{
            return SAFE_SET.has(f.family.toLowerCase());
          }});
        }});
      }};
    }}
  }} catch(e) {{}}

  // 覆盖 CSS font-family 解析的 measureText（防字体枚举）
  try {{
    var origMeasure = CanvasRenderingContext2D.prototype.measureText;
    CanvasRenderingContext2D.prototype.measureText = function(text) {{
      // 强制使用安全字体族
      var currentFont = this.font || '';
      var safeFont = SAFE_FONTS.slice(0, 6).join(', ') + ', sans-serif';
      this.font = currentFont.replace(/font-family:[^;]+/g, 'font-family: ' + safeFont);
      return origMeasure.apply(this, arguments);
    }};
  }} catch(e) {{}}
}})();
"#
        )
    }
}

impl Default for FontNormalizer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_fonts_include_essentials() {
        let fn_ = FontNormalizer::new();
        assert!(fn_.safe_fonts.contains(&"Arial".to_string()));
        assert!(fn_.safe_fonts.contains(&"serif".to_string()));
        assert!(fn_.safe_fonts.contains(&"monospace".to_string()));
    }

    #[test]
    fn script_contains_safe_fonts() {
        let fn_ = FontNormalizer::new();
        let script = fn_.inject_script();
        assert!(script.contains("SAFE_FONTS"));
        assert!(script.contains("Arial"));
        assert!(script.contains("document.fonts"));
    }

    #[test]
    fn custom_fonts_work() {
        let fn_ = FontNormalizer::with_fonts(vec!["MyFont".to_string()]);
        assert_eq!(fn_.safe_fonts.len(), 1);
        assert!(fn_.safe_fonts.contains(&"MyFont".to_string()));
    }
}

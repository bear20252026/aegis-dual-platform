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
        Self { safe_fonts: fonts }
    }

    /// 生成字体归一化 JS 注入脚本。
    ///
    /// 覆盖以下 API：
    /// - `document.fonts.check()` — 仅对安全字体返回 true
    /// - `document.fonts.values()` — 仅返回安全字体
    /// - CSS `font-family` 解析 — 仅匹配安全字体
    pub fn inject_script(&self) -> String {
        let fonts_json: String = {
            // RS-023（审计 2026-09-24）：自定义字体名含 `'`/`\` 此前直拼
            // 进 `'{}'` 字面量——逃逸字符串注入任意 JS
            let items: Vec<String> = self
                .safe_fonts
                .iter()
                .map(|f| format!("'{}'", crate::util::js_escape_single_quoted(f)))
                .collect();
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
      // RS-019（审计 2026-09-24）：剥除尺寸/样式前缀——canvas check 传参
      // 形如 "12px Arial" / "italic bold 12px 'Times New Roman'"，此前带
      // 尺寸前缀的 family 永不在 SAFE_SET 内 → check 对安全字体也返回
      // false（防护反向失效：安全字体被伪装成不可用）
      family = family.replace(
        /^(?:normal|italic|oblique|bold|[1-9]00\b)*\s*\d+(?:\.\d+)?[a-z%]*\s+/, '').trim();
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
      // RS-018（审计 2026-09-24）：canvas font 是 CSS 简写（"16px Arial"），
      // 不含 "font-family:" 前缀——旧 replace 永不命中（整体 no-op）。
      // 现解析简写尾部的 family 段并整段替换；解析失败则落到保守默认值
      var m = /^((?:normal|italic|oblique|bold|small-caps|[1-9]00)\s+)*(\d+(?:\.\d+)?(?:px|pt|pc|in|cm|mm|q|em|rem|ex|ch))(?:\s*\/\s*[\d.]+\S*)?\s+([\s\S]+)$/i.exec(currentFont);
      this.font = m ? (m[2] + ' ' + safeFont) : ('10px ' + safeFont);
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

    // —— RS-018/019/023 回归（审计 2026-09-24） ——

    #[test]
    fn check_strips_size_style_prefix() {
        // RS-019：check() 提取的 family 必须剥除尺寸/样式前缀——否则
        // "12px arial" 永不在 SAFE_SET 内，check 对安全字体也返回 false
        let script = FontNormalizer::new().inject_script();
        assert!(
            script.contains(r"\d+(?:\.\d+)?[a-z%]*"),
            "check() 必须包含尺寸前缀剥除正则"
        );
        assert!(
            !script.contains("currentFont.replace(/font-family:"),
            "旧 measureText 的 font-family 前缀替换必须已移除（永不含该前缀 = 死代码）"
        );
    }

    #[test]
    fn measure_text_parses_shorthand_family() {
        // RS-018：measureText 改为解析 CSS 简写尾部 family 段
        let script = FontNormalizer::new().inject_script();
        assert!(
            script.contains(r"(?:px|pt|pc|in|cm|mm|q|em|rem|ex|ch)"),
            "measureText 必须按 CSS 简写尺寸单位解析"
        );
        assert!(
            script.contains("m[2] + ' ' + safeFont"),
            "解析成功时保留原尺寸段、替换 family 段"
        );
        assert!(
            script.contains("'10px ' + safeFont"),
            "解析失败时落到保守默认尺寸"
        );
    }

    #[test]
    fn custom_font_name_escaped() {
        // RS-023：字体名单引号注入——直拼逃逸字符串字面量
        let fn_ = FontNormalizer::with_fonts(vec!["Foo'bar".to_string()]);
        let script = fn_.inject_script();
        assert!(script.contains("Foo\\'bar"), "单引号必须已转义");
        assert!(!script.contains("'Foo'bar'"), "不得残留未转义直拼");
    }
}

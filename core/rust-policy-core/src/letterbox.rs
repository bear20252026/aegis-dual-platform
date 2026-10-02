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
/// - RS-299（2026-10-02 审计）：本实现**仅圆整 JS 报告值**（screen/window
///   尺寸属性），不做 Tor 式 CSS padding 视觉 letterbox（内容区不加黑边、
///   窗口实际尺寸不变）——名实对齐，防误读为完整视觉 letterboxing
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
    ///
    /// RS-021（审计 2026-09-24）：步长钳到 ≥1——0 会让注入 JS 的
    /// `Math.round(v / step)` 除零得 Infinity（圆整完全失效）。
    pub fn with_config(config: LetterboxConfig) -> Self {
        Self {
            config: LetterboxConfig {
                width_step: config.width_step.max(1),
                height_step: config.height_step.max(1),
                ..config
            },
        }
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
  // RS-237（2026-09-26 审计）：screen 四属性补 .get 判定——此前仅判
  // descriptor 存在（if (osW)）即调用 osW.get.call(this)，数据属性形态
  // （get 为 undefined）下页面首读 screen.width 即抛 TypeError。
  // RS-250（2026-10-01 审计）：原型级替换——此前实例遮蔽
  // （defineProperty(screen, ...)）可经
  // Object.getOwnPropertyDescriptor(Screen.prototype, 'width').get.call(screen)
  // 直取原值（font_norm 口径统一）。保留原 descriptor 的
  // enumerable/configurable（属性形态对齐原生）
  try {{
    var osW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'width');
    var osH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'height');
    var osAW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availWidth');
    var osAH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availHeight');
    if (osW && osW.get) Object.defineProperty(window.Screen.prototype, 'width', {{ get: function() {{ return roundTo(osW.get.call(this), WS, MW); }}, enumerable: osW.enumerable, configurable: osW.configurable }});
    if (osH && osH.get) Object.defineProperty(window.Screen.prototype, 'height', {{ get: function() {{ return roundTo(osH.get.call(this), HS, MH); }}, enumerable: osH.enumerable, configurable: osH.configurable }});
    if (osAW && osAW.get) Object.defineProperty(window.Screen.prototype, 'availWidth', {{ get: function() {{ return roundTo(osAW.get.call(this), WS, MW); }}, enumerable: osAW.enumerable, configurable: osAW.configurable }});
    if (osAH && osAH.get) Object.defineProperty(window.Screen.prototype, 'availHeight', {{ get: function() {{ return roundTo(osAH.get.call(this), HS, MH); }}, enumerable: osAH.enumerable, configurable: osAH.configurable }});
  }} catch(e) {{}}

  // 覆盖 window 尺寸属性
  // RS-250：原型优先、实例兜底——innerWidth 等在部分引擎定义于
  // Window.prototype（此时实例遮蔽可被原型 getter 绕过），部分引擎为
  // window 自有 accessor。descriptor 命中哪个定义位就在哪替换，并保留
  // 原 enumerable/configurable 形态
  function aegisResolveProp(container, prop) {{
    var proto = container && container.prototype;
    if (proto) {{
      var pd = Object.getOwnPropertyDescriptor(proto, prop);
      if (pd) return {{ d: pd, target: proto }};
    }}
    return {{ d: container ? Object.getOwnPropertyDescriptor(container, prop) : null, target: container }};
  }}
  try {{
    // 先捕获原始 getter 再覆盖——若 getter 内再读 window.innerWidth，
    // 读到的已是覆盖后的自身，形成无限自递归栈溢出（RangeError）
    var oIW = aegisResolveProp(window.Window, 'innerWidth');
    var oIH = aegisResolveProp(window.Window, 'innerHeight');
    var oOW = aegisResolveProp(window.Window, 'outerWidth');
    var oOH = aegisResolveProp(window.Window, 'outerHeight');
    if (oIW.d && oIW.d.get) Object.defineProperty(oIW.target, 'innerWidth', {{ get: function() {{ return roundTo(oIW.d.get.call(this), WS, MW); }}, enumerable: oIW.d.enumerable, configurable: oIW.d.configurable }});
    if (oIH.d && oIH.d.get) Object.defineProperty(oIH.target, 'innerHeight', {{ get: function() {{ return roundTo(oIH.d.get.call(this), HS, MH); }}, enumerable: oIH.d.enumerable, configurable: oIH.d.configurable }});
    if (oOW.d && oOW.d.get) Object.defineProperty(oOW.target, 'outerWidth', {{ get: function() {{ return roundTo(oOW.d.get.call(this), WS, MW); }}, enumerable: oOW.d.enumerable, configurable: oOW.d.configurable }});
    if (oOH.d && oOH.d.get) Object.defineProperty(oOH.target, 'outerHeight', {{ get: function() {{ return roundTo(oOH.d.get.call(this), HS, MH); }}, enumerable: oOH.d.enumerable, configurable: oOH.d.configurable }});
  }} catch(e) {{}}

  // RS-079（审计 2026-09-25）：色深与 DPR 同属屏幕指纹面——colorDepth/
  // pixelDepth 固定 24（Tor 标准口径），DPR 圆整到 0.25 步长。
  // RS-250：colorDepth/pixelDepth 同步升级为原型级（原生定义于
  // Screen.prototype，实例遮蔽可被原型 getter 绕过）
  try {{
    var oCD = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'colorDepth');
    if (oCD) Object.defineProperty(window.Screen.prototype, 'colorDepth', {{ get: function() {{ return 24; }}, enumerable: oCD.enumerable, configurable: oCD.configurable }});
    var oPD = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'pixelDepth');
    if (oPD) Object.defineProperty(window.Screen.prototype, 'pixelDepth', {{ get: function() {{ return 24; }}, enumerable: oPD.enumerable, configurable: oPD.configurable }});
  }} catch(e) {{}}
  try {{
    // RS-293（2026-10-02 审计）：DPR 走 aegisResolveProp 原型优先解析
    //（对齐 innerWidth 组口径）——此前只查 window 自有 descriptor，
    // 定义于 Window.prototype 的引擎整个覆盖不生效（实例位无 descriptor
    // 即静默跳过，DPR 原值裸奔）
    var oDPR = aegisResolveProp(window.Window, 'devicePixelRatio');
    if (oDPR.d && oDPR.d.get) Object.defineProperty(oDPR.target, 'devicePixelRatio', {{
      get: function() {{ return Math.round(oDPR.d.get.call(this) * 4) / 4; }},
      enumerable: oDPR.d.enumerable,
      configurable: oDPR.d.configurable
    }});
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
    fn window_override_captures_original_getter() {
        // RS-001 回归：window 属性覆盖必须先捕获原 getter，
        // 不得在 getter 内再读同名属性（无限自递归栈溢出）。
        // RS-250：原型优先解析（aegisResolveProp）后仍以捕获的 descriptor
        // getter 为准
        let script = LetterboxShield::new().inject_script();
        assert!(script.contains("aegisResolveProp(window.Window, 'innerWidth')"));
        assert!(script.contains("aegisResolveProp(window.Window, 'outerHeight')"));
        // 覆盖体内不允许出现"读覆盖目标自身"的递归形态
        assert!(!script.contains("return roundTo(window.innerWidth"));
        assert!(!script.contains("return roundTo(window.innerHeight"));
    }

    #[test]
    fn every_override_guarded_by_descriptor_existence() {
        // RS-163（审计 2026-09-25）：descriptor 缺失时必须跳过对应覆盖——
        // 无守卫的 defineProperty 会以 undefined 原值覆盖（roundTo(undefined)
        // 产出 NaN，或用空覆盖反成指纹异常信号）。逐属性断言守卫形态：
        // RS-237（2026-09-26）：screen 组与 window 组统一双守卫
        //（descriptor 存在且 .get 可读——数据属性形态首读即 TypeError）。
        let script = LetterboxShield::new().inject_script();
        // RS-237：screen 四属性升级为双守卫（descriptor 存在且可读——
        // 数据属性形态下 .get 为 undefined，首读即 TypeError）
        for guard in [
            "if (osW && osW.get)",
            "if (osH && osH.get)",
            "if (osAW && osAW.get)",
            "if (osAH && osAH.get)",
        ] {
            assert!(
                script.contains(guard),
                "screen override missing guard {guard}"
            );
        }
        // window 四属性：if (oX.d && oX.d.get) 双守卫（RS-250：resolve 结构
        // 携带 descriptor + 定义位目标，守卫形态同步升级）
        for guard in [
            "if (oIW.d && oIW.d.get)",
            "if (oIH.d && oIH.d.get)",
            "if (oOW.d && oOW.d.get)",
            "if (oOH.d && oOH.d.get)",
        ] {
            assert!(
                script.contains(guard),
                "window override missing guard {guard}"
            );
        }
        // 色深与 DPR 组：同样不得裸 defineProperty
        assert!(
            script.contains("if (oCD)"),
            "colorDepth override missing guard"
        );
        assert!(
            script.contains("if (oPD)"),
            "pixelDepth override missing guard"
        );
        assert!(
            script.contains("if (oDPR.d && oDPR.d.get)"),
            "DPR override missing guard"
        );
        // 守卫与 defineProperty 一一配对：每个守卫行之后紧跟 defineProperty，
        // 不存在无守卫的裸覆盖（形态锁定，防未来新增属性漏写守卫）。
        for line in script.lines() {
            let trimmed = line.trim_start();
            if trimmed.starts_with("Object.defineProperty") {
                panic!("unguarded defineProperty found: {trimmed}");
            }
        }
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

    // —— RS-250 回归（审计 2026-10-01）：原型级替换 ——

    #[test]
    fn screen_properties_replaced_at_prototype_level() {
        // RS-250：screen 六属性（width/height/availWidth/availHeight/
        // colorDepth/pixelDepth）必须在 Screen.prototype 替换——实例遮蔽
        // （defineProperty(screen, ...)）可经原型 descriptor 的原 getter
        // 直取原值（font_norm 口径统一）
        let script = LetterboxShield::new().inject_script();
        for prop in [
            "width",
            "height",
            "availWidth",
            "availHeight",
            "colorDepth",
            "pixelDepth",
        ] {
            assert!(
                script.contains(&format!(
                    "Object.defineProperty(window.Screen.prototype, '{prop}'"
                )),
                "screen.{prop} 必须原型级替换"
            );
        }
        assert!(
            !script.contains("defineProperty(screen, '"),
            "实例遮蔽形态必须全部移除"
        );
        // 保留原 descriptor 属性（形态对齐原生）
        assert!(script.contains("enumerable: osW.enumerable"));
        assert!(script.contains("configurable: osW.configurable"));
        // window 组：原型优先、实例兜底（引擎定义位差异兼容）
        assert!(script.contains("aegisResolveProp(window.Window, 'innerWidth')"));
        assert!(script.contains("enumerable: oIW.d.enumerable"));
    }

    #[test]
    fn debug_format_shows_dimensions() {
        let shield = LetterboxShield::new();
        let debug = format!("{:?}", shield);
        assert!(debug.contains("200"));
        assert!(debug.contains("100"));
    }

    // —— RS-078 回归（审计 2026-09-25） ——

    #[test]
    fn zero_step_saturates_to_one() {
        // RS-078/RS-021：步长 0 钳到 1——否则 JS 侧 v/0 = Infinity 圆整失效
        let config = LetterboxConfig {
            width_step: 0,
            height_step: 0,
            min_width: 1,
            min_height: 1,
        };
        let script = LetterboxShield::with_config(config).inject_script();
        assert!(script.contains("var WS = 1,"), "宽步长钳到 1");
        assert!(script.contains("HS = 1,"), "高步长钳到 1");
    }

    #[test]
    fn round_to_clamps_to_minimum() {
        // RS-078：roundTo 必须带 minV 下限钳制（小窗口不得圆整到 0）
        let script = LetterboxShield::new().inject_script();
        assert!(
            script.contains("Math.max(minV, Math.round(v / step) * step)"),
            "roundTo 钳制语义"
        );
    }

    // —— RS-079 回归（审计 2026-09-25） ——

    #[test]
    fn color_depth_and_dpr_covered() {
        // RS-079：色深固定 24 + DPR 0.25 步长圆整
        let script = LetterboxShield::new().inject_script();
        assert!(script.contains("'colorDepth'"), "colorDepth 覆盖");
        assert!(script.contains("'pixelDepth'"), "pixelDepth 覆盖");
        assert!(script.contains("return 24;"), "色深固定 24（Tor 口径）");
        assert!(
            script.contains("'devicePixelRatio'"),
            "devicePixelRatio 覆盖"
        );
        assert!(
            script.contains("Math.round(oDPR.d.get.call(this) * 4) / 4"),
            "DPR 圆整到 0.25 步长"
        );
    }

    // —— RS-293/299 回归（2026-10-02 审计） ——

    #[test]
    fn dpr_resolved_prototype_first_like_inner_width_group() {
        // RS-293：devicePixelRatio 此前只查 window 自有 descriptor——定义
        // 于 Window.prototype 的引擎整个覆盖不生效。现走 aegisResolveProp
        // 原型优先解析（对齐 innerWidth 组）
        let script = LetterboxShield::new().inject_script();
        assert!(
            script.contains("aegisResolveProp(window.Window, 'devicePixelRatio')"),
            "DPR 必须原型优先解析"
        );
        assert!(
            !script.contains("Object.getOwnPropertyDescriptor(window, 'devicePixelRatio')"),
            "实例位直查形态不得残留"
        );
        assert!(
            script.contains("Object.defineProperty(oDPR.target, 'devicePixelRatio'"),
            "定义位随解析结果替换（原型/实例自适应）"
        );
    }

    #[test]
    fn doc_comment_does_not_claim_visual_css_letterbox() {
        // RS-299：文档此前描述「内容区域用 CSS padding 填充」的视觉
        // letterbox——实际只圆整 JS 报告值（无 CSS padding、无黑边）。
        // 名实对齐：文档不得残留 CSS padding 声称。断言串经 concat 构造
        //（直写字面量会被 include_str 的测试自身命中）
        let source = include_str!("letterbox.rs");
        let forbidden = ["内容区域用 CSS padding ", "填充到实际窗口尺寸"].concat();
        assert!(
            !source.contains(&forbidden),
            "不得残留 CSS padding 视觉 letterbox 声称（实现只圆整 JS 报告值）"
        );
        let required = ["仅圆整 ", "JS 报告值"].concat();
        assert!(
            source.contains(&required),
            "文档必须如实声明只圆整 JS 报告值"
        );
    }
}

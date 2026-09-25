// 由账号2生成
//! WebGLSpoof（参照 playwright-afp WebGL 指纹防护）。
//!
//! 固定 WebGL 参数为常见值，防止基于 GPU 硬件信息的指纹识别。
//! 包括 vendor/renderer 字符串伪装和硬件限制伪装。
//!
//! 原始版权声明：
//!   playwright-afp by pavlealeksic (MIT License)
//!   https://github.com/pavlealeksic/playwright-afp
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 FingerprintShield 管线中作为独立阶段调用。

use std::fmt;

/// WebGL 参数伪装配置。
#[derive(Debug, Clone)]
pub struct WebGLSpoofConfig {
    /// 伪装的 vendor 字符串。
    pub vendor: String,
    /// 伪装的 renderer 字符串。
    pub renderer: String,
    /// 最大纹理尺寸（伪装值）。
    pub max_texture_size: u32,
    /// 最大视口尺寸（伪装值）。
    pub max_viewport_dims: [u32; 2],
    /// 最大渲染缓冲区大小（伪装值）。
    pub max_renderbuffer_size: u32,
}

impl Default for WebGLSpoofConfig {
    fn default() -> Self {
        Self {
            vendor: "Google Inc. (Intel)".to_string(),
            renderer: "ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)".to_string(),
            max_texture_size: 16384,
            max_viewport_dims: [16384, 16384],
            max_renderbuffer_size: 16384,
        }
    }
}

/// WebGLSpoof — WebGL 参数伪装。
///
/// 覆盖 WebGL 上下文的 getParameter 返回值，
/// 使所有用户报告相同的 GPU 信息。
pub struct WebGLSpoof {
    config: WebGLSpoofConfig,
}

impl fmt::Debug for WebGLSpoof {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "WebGLSpoof(vendor={})", self.config.vendor)
    }
}

impl WebGLSpoof {
    /// 用默认配置创建（Intel UHD Graphics 620——最常见的 GPU）。
    pub fn new() -> Self {
        Self {
            config: WebGLSpoofConfig::default(),
        }
    }

    /// 用自定义配置创建。
    pub fn with_config(config: WebGLSpoofConfig) -> Self {
        Self { config }
    }

    /// 生成 WebGL 参数伪装 JS 注入脚本。
    ///
    /// 覆盖：
    /// - `WebGLRenderingContext.getParameter()` — vendor/renderer/硬件限制
    /// - `WebGL2RenderingContext.getParameter()` — 同上
    /// - `WEBGL_debug_renderer_info` 扩展参数
    pub fn inject_script(&self) -> String {
        // RS-024（审计 2026-09-24）：vendor/renderer 含 `'`/`\` 此前直拼进
        // `'{}'` 字面量——逃逸字符串注入任意 JS
        let vendor = crate::util::js_escape_single_quoted(&self.config.vendor);
        let renderer = crate::util::js_escape_single_quoted(&self.config.renderer);
        let max_tex = self.config.max_texture_size;
        let max_vp_w = self.config.max_viewport_dims[0];
        let max_vp_h = self.config.max_viewport_dims[1];
        let max_rb = self.config.max_renderbuffer_size;
        format!(
            r#"
// Aegis WebGLSpoof — WebGL 参数伪装（参照 playwright-afp）
// 原始设计：pavlealeksic/playwright-afp (MIT License)
// 固定 WebGL vendor/renderer/硬件限制为常见值
(function() {{
  // WebGL 常量
  var UNMASKED_VENDOR_WEBGL = 0x9245;   // 37445
  var UNMASKED_RENDERER_WEBGL = 0x9246; // 37446
  var VENDOR = 0x1F00;                   // 7936
  var RENDERER = 0x1F01;                 // 7937
  var MAX_TEXTURE_SIZE = 0x0D33;         // 3379
  var MAX_VIEWPORT_DIMS = 0x0D3A;        // 3386
  var MAX_RENDERBUFFER_SIZE = 0x84E8;    // 34024

  var vendorStr = '{vendor}';
  var rendererStr = '{renderer}';
  var maxTexSize = {max_tex};
  var maxViewportW = {max_vp_w};
  var maxViewportH = {max_vp_h};
  var maxRenderbuf = {max_rb};

  function patchContext(proto) {{
    // RS-076（审计 2026-09-25）：viewport 数组缓存单实例——此前每次
    // getParameter(MAX_VIEWPORT_DIMS) 都 new Int32Array，页面连续两次
    // 调用做 Object.is 恒为 false（对象身份漂移可被检测；真实 GL 实现
    // 的该参数返回值引用稳定）
    var viewportDims = new Int32Array([maxViewportW, maxViewportH]);
    // RS-077（审计 2026-09-25）：扩展列表泄露 GPU 型号特征（特定 GPU
    // 独有扩展组合）——debug_renderer_info 由 getParameter 伪装通道
    // 单一负责，扩展查询面直接摘除
    var origGetSupported = proto.getSupportedExtensions;
    proto.getSupportedExtensions = function() {{
      var exts = origGetSupported.call(this) || [];
      return exts.filter(function(e) {{ return e !== 'WEBGL_debug_renderer_info'; }});
    }};
    var origGetExtension = proto.getExtension;
    proto.getExtension = function(name) {{
      if (name === 'WEBGL_debug_renderer_info') return null;
      return origGetExtension.call(this, name);
    }};
    var origGetParam = proto.getParameter;
    proto.getParameter = function(param) {{
      switch(param) {{
        case UNMASKED_VENDOR_WEBGL:
        case VENDOR:
          return vendorStr;
        case UNMASKED_RENDERER_WEBGL:
        case RENDERER:
          return rendererStr;
        case MAX_TEXTURE_SIZE:
          return maxTexSize;
        case MAX_VIEWPORT_DIMS:
          return viewportDims; // RS-076：单实例，对象身份稳定
        case MAX_RENDERBUFFER_SIZE:
          return maxRenderbuf;
        default:
          return origGetParam.call(this, param);
      }}
    }};
    // 注册代理——toString 防护映射此包装，防"检测函数被覆盖"识破
    var reg3 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg3) reg3(proto.getParameter, origGetParam);
    var reg4 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg4) reg4(proto.getSupportedExtensions, origGetSupported);
    var reg5 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg5) reg5(proto.getExtension, origGetExtension);
  }}

  try {{ patchContext(WebGLRenderingContext.prototype); }} catch(e) {{}}
  try {{ patchContext(WebGL2RenderingContext.prototype); }} catch(e) {{}}
}})();
"#
        )
    }
}

impl Default for WebGLSpoof {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_has_common_gpu() {
        let config = WebGLSpoofConfig::default();
        assert!(config.vendor.contains("Intel"));
        assert!(config.renderer.contains("UHD Graphics"));
    }

    #[test]
    fn script_contains_spoof_values() {
        let spoof = WebGLSpoof::new();
        let script = spoof.inject_script();
        assert!(script.contains("UNMASKED_VENDOR_WEBGL"));
        assert!(script.contains("UNMASKED_RENDERER_WEBGL"));
        assert!(script.contains("getParameter"));
        assert!(script.contains("16384"));
    }

    #[test]
    fn custom_config_reflected() {
        let config = WebGLSpoofConfig {
            vendor: "NVIDIA".to_string(),
            renderer: "GeForce RTX 3080".to_string(),
            ..Default::default()
        };
        let spoof = WebGLSpoof::with_config(config);
        let script = spoof.inject_script();
        assert!(script.contains("NVIDIA"));
        assert!(script.contains("RTX 3080"));
    }

    // —— RS-075 回归（审计 2026-09-25） ——

    #[test]
    fn custom_viewport_dims_rendered() {
        // RS-075：自定义视口值透传（含非常规值）+ Int32Array 类型契约
        let config = WebGLSpoofConfig {
            max_viewport_dims: [4096, 8192],
            ..Default::default()
        };
        let script = WebGLSpoof::with_config(config).inject_script();
        // 值经 maxViewportW/H 变量行透传，viewportDims 缓存引用变量
        assert!(script.contains("var maxViewportW = 4096;"), "宽值透传");
        assert!(script.contains("var maxViewportH = 8192;"), "高值透传");
        assert!(
            script.contains("var viewportDims = new Int32Array"),
            "类型契约"
        );
    }

    #[test]
    fn viewport_array_identity_stable() {
        // RS-076：viewport 数组必须缓存单实例——每次 new 的对象身份漂移
        //（Object.is 恒 false）可被页面检测
        let script = WebGLSpoof::new().inject_script();
        // 单实例缓存：构造一次，case 分支只返回变量
        assert!(script.contains("var viewportDims = new Int32Array"));
        assert!(
            !script.contains("return new Int32Array"),
            "getParameter 体内不得每次分配新数组"
        );
        assert!(script.contains("return viewportDims;"));
    }

    #[test]
    fn extension_enumeration_surface_removed() {
        // RS-077：扩展枚举面摘除 debug_renderer_info——vendor/renderer
        // 仅经 getParameter 伪装通道暴露
        let script = WebGLSpoof::new().inject_script();
        assert!(script.contains("getSupportedExtensions"), "扩展列表覆盖");
        assert!(
            script.contains("e !== 'WEBGL_debug_renderer_info'"),
            "扩展列表过滤 debug_renderer_info"
        );
        assert!(
            script.contains("if (name === 'WEBGL_debug_renderer_info') return null;"),
            "getExtension 对 debug_renderer_info 返回 null"
        );
    }
}

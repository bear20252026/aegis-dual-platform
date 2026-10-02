//! FingerprintShield（照搬 voidbrowser privacy/fingerprint.rs 本地化适配）。
//!
//! 每会话生成加密随机种子，用于确定性地注入 JS 指纹噪声。
//! 所有 WebView 共享同一个会话种子，每次启动刷新。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：WebView 创建时调用 `inject_script()` 注入 JS。

use std::fmt;

/// 指纹防护种子（32 字节加密随机）。
#[derive(Clone)]
pub struct FingerprintShield {
    seed: [u8; 32],
}

impl fmt::Debug for FingerprintShield {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "FingerprintShield(seed=***hidden***)")
    }
}

impl FingerprintShield {
    /// 用系统加密随机源创建新会话种子。
    /// 此前用 SystemTime 纳秒 × PID 推导——完全可预测且 (i%16)*8 移位使
    /// 字节 0-15 与 16-31 相同（有效熵 ≤128bit 且结构相关），指纹噪声
    /// 可被外部推算复现。现在直接取 OS CSPRNG。
    pub fn new() -> Self {
        let mut seed = [0u8; 32];
        // RS-153：getrandom 0.3 API——getrandom() 更名 fill()
        if getrandom::fill(&mut seed).is_err() {
            // OS 随机源不可用（极端环境）——退化为时间+PID 混合（仍填充全部
            // 32 字节，高低半区经旋转与异或折叠去相关）
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            let pid = std::process::id() as u128;
            for (i, byte) in seed.iter_mut().enumerate() {
                let mut val = nanos ^ (pid << 32) ^ ((i as u128) << 24);
                val = val
                    .wrapping_mul(0x9E37_79B9_7F4A_7C15)
                    .rotate_right(((i * 7) % 128) as u32);
                *byte = (val as u8) ^ ((val >> 64) as u8) ^ (i as u8);
            }
        }
        Self { seed }
    }

    /// 从已有种子恢复（用于持久化/测试）。
    pub fn from_seed(seed: [u8; 32]) -> Self {
        Self { seed }
    }

    /// 种子的十六进制表示（注入 JS 时用）。
    ///
    /// RS-262（2026-10-01 审计）：收敛到 util::hex_encode 单源——此处逐字节
    /// format! 是 crate 内第三份 hex 实现（util::hex_encode / ffi/broker 查表
    /// 特化之外又一份），口径漂移面。
    pub fn seed_hex(&self) -> String {
        crate::util::hex_encode(&self.seed)
    }

    /// 种子的原始字节（供 PerSiteSeed 等管道阶段使用）。
    pub fn seed_bytes(&self) -> [u8; 32] {
        self.seed
    }

    /// 生成 JS 注入脚本（注入 WebView——canvas/Audio 噪声）。
    ///
    /// 种子以闭包内局部常量注入——**不再置于顶层全局词法环境**（此前顶层
    /// `const __AEGIS_SESSION_SEED` 任意页面可按名读取，全会话跨站唯一
    /// 标识符等于主动发放的超级 Cookie）。
    ///
    /// RS-026（审计 2026-09-24）：WebGL vendor/renderer 伪装已移出本模块——
    /// webgl_spoof 是该能力的单一负责方（此前两处覆盖同两个常量但取值
    /// 口径矛盾，后者静默遮蔽前者）。Canvas 噪声为本模块职责保留。
    ///
    /// RS-207（2026-09-26 审计）：canvas 噪声种子**按站点派生**——此前直接
    /// 取会话级常量 `__AEGIS_SESSION_SEED.slice(0,8)`，同一用户同会话访问
    /// A/B 两站噪声图案完全相同，站点比对 canvas 哈希即可跨站关联。
    /// 站点键在运行时由 `location.hostname`（eTLD+1）混合会话种子派生
    /// （与 Android 孪生 WebViewHardening 的 getETLD1+deriveSeed 同口径）；
    /// 页面无法伪造 location.hostname（变更即触发导航），注入入口无需
    /// 宿主额外传域。AudioBuffer 通道的 per-site 隔离由 PerSiteSeed 阶段
    /// （Rust 侧 SHA-256 派生）负责。
    pub fn inject_script(&self) -> String {
        let hex = self.seed_hex();
        // RS-218（2026-09-26 审计）：代理注册接口 Symbol 键单源引用
        //（描述串去品牌化——详见 ToStringGuard::REGISTER_SYMBOL）
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
        format!(
            r#"
// Aegis FingerprintShield — 每会话确定性噪声种子（闭包封装——不进全局作用域）
(function() {{
  const __AEGIS_SESSION_SEED = '{hex}';

  // RS-207（2026-09-26 审计）：canvas 噪声站点键——FNV-1a 域混合 + 两轮
  // xorshift 雪崩；同站同会话确定（噪声稳定），跨站/跨会话去相关
  // RS-257（2026-10-01 审计）：eTLD+1 提取带最小公共后缀表——此前固定取
  // 最后两标签，a.co.uk 与 b.co.uk 共享种子（跨站关联面）。末两标签命中
  // 公共后缀表时升到三标签（公共后缀本身不构成站点边界）
  var AEGIS_PUBLIC_SUFFIXES = {{
    'co.uk': 1, 'org.uk': 1, 'ac.uk': 1, 'gov.uk': 1,
    'com.au': 1, 'net.au': 1, 'org.au': 1, 'edu.au': 1,
    'co.jp': 1, 'ne.jp': 1, 'or.jp': 1, 'ac.jp': 1,
    'com.br': 1, 'com.cn': 1, 'net.cn': 1, 'org.cn': 1,
    'com.tw': 1, 'com.hk': 1, 'com.sg': 1, 'co.nz': 1, 'co.za': 1,
    'github.io': 1, 'gitlab.io': 1, 'pages.dev': 1, 'vercel.app': 1,
    'netlify.app': 1, 'appspot.com': 1, 'blogspot.com': 1,
    'herokuapp.com': 1, 'azurewebsites.net': 1, 'cloudfront.net': 1
  }};
  function aegisEtldPlus1(host) {{
    var parts = host.split('.');
    if (parts.length <= 2) return host;
    var last2 = parts.slice(-2).join('.');
    if (AEGIS_PUBLIC_SUFFIXES[last2] && parts.length >= 3) {{
      return parts.slice(-3).join('.');
    }}
    return last2;
  }}
  function aegisCanvasSeed() {{
    var etld1 = aegisEtldPlus1(location.hostname || '');
    var h = 2166136261 >>> 0;
    for (var i = 0; i < etld1.length; i++) {{
      h = Math.imul(h ^ etld1.charCodeAt(i), 16777619) >>> 0;
      h = (h ^ __AEGIS_SESSION_SEED.charCodeAt(i % 64)) >>> 0;
    }}
    h ^= h >>> 15; h = Math.imul(h, 2246822519) >>> 0;
    h ^= h >>> 13; h = Math.imul(h, 3266489917) >>> 0;
    h ^= h >>> 16;
    return h >>> 0;
  }}

  // Canvas 噪声（每个像素 ±1 随机偏移——视觉不可察觉）
  // RS-025（审计 2026-09-24）：噪声施加在**离屏副本**上——此前就地
  // putImageData 把噪声写回原画布，页面双读（toDataURL 前后各 getImageData
  // 一次）即可检测像素漂移
  // RS-206（2026-09-26 审计）：删除源画布的 getContext('2d')
  // 前置门禁——①画布已持 WebGL 上下文时 getContext('2d') 返回 null，
  // 噪声被整体绕过（WebGL 画布恰是主流指纹向量）；②画布尚无上下文时
  // 该调用会把画布永久锁定为 2d（页面随后 getContext('webgl') 得 null，
  // 渲染被破坏）。drawImage(this) 对任意上下文类型的源画布均可用，
  // 离屏副本自取 2d 上下文即可
  (function() {{
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {{
      try {{
        const off = document.createElement('canvas');
        off.width = this.width;
        off.height = this.height;
        const octx = off.getContext('2d');
        octx.drawImage(this, 0, 0);
        const imageData = octx.getImageData(0, 0, off.width, off.height);
        const seed = aegisCanvasSeed();
        for (let i = 0; i < imageData.data.length; i += 4) {{
          // RS-215（2026-09-26 审计）：R/G/B 三通道扰动（对齐 Android
          // AD-175 多通道口径）；alpha 不动（透明度变化视觉可察）
          // RS-249（2026-10-01 审计）：逐像素混合——(seed+i)%N 在 i+=4 步进下
          // 每通道全图只取一个常量偏置（整图减法即还原，与 Android AD-253
          // 同病）。改为像素索引与种子经 Math.imul 混合取最低位，三通道
          // 不同常数（0x9E3779B1 / 0x85EBCA6B / 0x27D4EB2F）——逐像素
          // 0/1 扰动（Android 侧将实现等价口径，不要求字节级一致）
          imageData.data[i] += (((seed ^ Math.imul(i, 0x9E3779B1)) >>> 0) & 1) ? 1 : -1;
          imageData.data[i + 1] += (((seed ^ Math.imul(i, 0x85EBCA6B)) >>> 0) & 1) ? 1 : -1;
          imageData.data[i + 2] += (((seed ^ Math.imul(i, 0x27D4EB2F)) >>> 0) & 1) ? 1 : -1;
        }}
        octx.putImageData(imageData, 0, 0);
        return origToDataURL.apply(off, arguments);
      }} catch (e) {{}}
      return origToDataURL.apply(this, arguments);
    }};
  if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](HTMLCanvasElement.prototype.toDataURL, origToDataURL);
}})();

// RS-082（审计 2026-09-25）：toBlob 是 canvas 读取的第二通道——仅覆盖
// toDataURL 时页面走 toBlob 拿到无噪声原图。同型离屏副本 + 噪声
//（RS-206/207/215 口径与 toDataURL 通道一致）
(function() {{
  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
    try {{
      const off = document.createElement('canvas');
      off.width = this.width;
      off.height = this.height;
      const octx = off.getContext('2d');
      octx.drawImage(this, 0, 0);
      const imageData = octx.getImageData(0, 0, off.width, off.height);
      const seed = aegisCanvasSeed();
      for (let i = 0; i < imageData.data.length; i += 4) {{
        // RS-249：逐像素 Math.imul 混合（三通道不同常数）——(seed+i)%N 形态
        // 在 i+=4 步进下退化为通道常量偏置；口径与 toDataURL 通道一致
        imageData.data[i] += (((seed ^ Math.imul(i, 0x9E3779B1)) >>> 0) & 1) ? 1 : -1;
        imageData.data[i + 1] += (((seed ^ Math.imul(i, 0x85EBCA6B)) >>> 0) & 1) ? 1 : -1;
        imageData.data[i + 2] += (((seed ^ Math.imul(i, 0x27D4EB2F)) >>> 0) & 1) ? 1 : -1;
      }}
      octx.putImageData(imageData, 0, 0);
      return origToBlob.call(off, callback, type, quality);
    }} catch (e) {{}}
    return origToBlob.call(this, callback, type, quality);
  }};
  if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](HTMLCanvasElement.prototype.toBlob, origToBlob);
}})();

// RS-082：OffscreenCanvas.convertToBlob 是 worker 侧第三通道——同型防护
//（RS-206/207/215 口径与 toDataURL 通道一致）
(function() {{
  if (typeof OffscreenCanvas === 'undefined') return;
  const origConvert = OffscreenCanvas.prototype.convertToBlob;
  OffscreenCanvas.prototype.convertToBlob = function(options) {{
    try {{
      const off = new OffscreenCanvas(this.width, this.height);
      const octx = off.getContext('2d');
      octx.drawImage(this, 0, 0);
      const imageData = octx.getImageData(0, 0, off.width, off.height);
      const seed = aegisCanvasSeed();
      for (let i = 0; i < imageData.data.length; i += 4) {{
        // RS-249：逐像素 Math.imul 混合（三通道不同常数）——(seed+i)%N 形态
        // 在 i+=4 步进下退化为通道常量偏置；口径与 toDataURL 通道一致
        imageData.data[i] += (((seed ^ Math.imul(i, 0x9E3779B1)) >>> 0) & 1) ? 1 : -1;
        imageData.data[i + 1] += (((seed ^ Math.imul(i, 0x85EBCA6B)) >>> 0) & 1) ? 1 : -1;
        imageData.data[i + 2] += (((seed ^ Math.imul(i, 0x27D4EB2F)) >>> 0) & 1) ? 1 : -1;
      }}
      octx.putImageData(imageData, 0, 0);
      return origConvert.call(off, options);
    }} catch (e) {{}}
    return origConvert.call(this, options);
  }};
  if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](OffscreenCanvas.prototype.convertToBlob, origConvert);
}})();

// 音频指纹噪声由 PerSiteSeed（RS-028）负责——按站点隔离，不在此模块重复

// hardwareConcurrency 随机化（2-8 核）
// RS-250（2026-10-01 审计）：原型级 getter 替换——此前实例遮蔽
// （defineProperty(navigator, ...)）可经
// Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency')
// .get.call(navigator) 直取原值（与 letterbox/font_norm 口径统一为原型级）。
// 保留原 descriptor 的 enumerable/configurable（属性形态对齐原生）
(function() {{
  const seed = parseInt(__AEGIS_SESSION_SEED.slice(8, 16), 16);
  var oHC = Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency');
  if (oHC && oHC.get) {{
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
      get: function() {{ return 2 + (seed % 7); }},
      enumerable: oHC.enumerable,
      configurable: oHC.configurable
    }});
  }}
}})();
}})();
"#
        )
    }
}

impl Default for FingerprintShield {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seed_is_32_bytes_hex() {
        let s = FingerprintShield::new();
        assert_eq!(s.seed_hex().len(), 64); // 32 bytes = 64 hex chars
    }

    #[test]
    fn script_contains_seed_marker() {
        let s = FingerprintShield::new();
        let script = s.inject_script();
        assert!(script.contains("__AEGIS_SESSION_SEED"));
        assert!(script.contains("toDataURL"));
        assert!(script.contains("hardwareConcurrency"));
    }

    #[test]
    fn two_instances_have_different_seeds() {
        let a = FingerprintShield::new();
        let b = FingerprintShield::new();
        assert_ne!(a.seed_hex(), b.seed_hex());
    }

    #[test]
    fn from_seed_deterministic() {
        let seed = [42u8; 32];
        let a = FingerprintShield::from_seed(seed);
        let b = FingerprintShield::from_seed(seed);
        assert_eq!(a.seed_hex(), b.seed_hex());
    }

    // —— RS-081 回归（审计 2026-09-25） ——

    #[test]
    fn debug_does_not_leak_seed() {
        // RS-081：Debug 输出绝不泄种子（日志/崩溃报告面泄漏 = 会话级
        // 指纹标识符外泄）
        let s = FingerprintShield::from_seed([0xabu8; 32]);
        let debug = format!("{s:?}");
        assert!(debug.contains("***hidden***"), "Debug 遮蔽语义");
        assert!(!debug.contains("ababab"), "Debug 不得含种子 hex 片段");
        // inject_script 确定性：同种子两次生成逐字节一致
        assert_eq!(s.inject_script(), s.inject_script());
    }

    #[test]
    fn seed_bytes_roundtrip_matches_hex() {
        // RS-081：seed_bytes 与 seed_hex 同源一致（管线阶段消费契约）；
        // RS-262：seed_hex 已收敛 util::hex_encode 单源——期望值同源构造
        let seed = [7u8; 32];
        let s = FingerprintShield::from_seed(seed);
        assert_eq!(s.seed_bytes(), seed);
        let hex_from_bytes = crate::util::hex_encode(&s.seed_bytes());
        assert_eq!(hex_from_bytes, s.seed_hex());
    }

    // —— RS-082 回归（审计 2026-09-25） ——

    #[test]
    fn canvas_read_channels_all_covered() {
        // RS-082：canvas 读取三通道全覆盖——toDataURL/toBlob/
        // OffscreenCanvas.convertToBlob（漏任一通道 = 噪声绕过）
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        assert!(script.contains("HTMLCanvasElement.prototype.toDataURL"));
        assert!(
            script.contains("HTMLCanvasElement.prototype.toBlob"),
            "toBlob 第二通道必须覆盖"
        );
        assert!(
            script.contains("OffscreenCanvas.prototype.convertToBlob"),
            "convertToBlob 第三通道必须覆盖"
        );
        assert!(
            script.contains("音频指纹噪声由 PerSiteSeed"),
            "Audio 归属文档化（PerSiteSeed 单一负责）"
        );
    }

    // —— RS-206/207/215 回归（审计 2026-09-26） ——

    #[test]
    fn canvas_noise_not_gated_on_source_2d_context() {
        // RS-206：噪声包装不得对源画布调用 this.getContext('2d')——
        // WebGL 画布（主流指纹向量）取 2d 上下文得 null 会整体绕过噪声；
        // 无上下文画布则被永久锁定 2d（页面后续 webgl 渲染被破坏）。
        // 离屏副本自身的 off.getContext('2d') 不受影响（副本自建 2d 上下文）
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        assert!(
            !script.contains("this.getContext"),
            "噪声包装不得探测源画布上下文（WebGL 画布噪声绕过 + 2d 锁定）"
        );
        assert!(
            script.contains("off.getContext('2d')"),
            "离屏副本自取 2d 上下文（drawImage 通道）"
        );
    }

    #[test]
    fn canvas_noise_seed_is_per_site() {
        // RS-207：canvas 噪声种子必须按站点派生——会话级常量种子对同会话
        // 的 A/B 两站产生相同噪声图案（跨站 canvas 哈希比对即关联用户）
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        assert!(
            script.contains("location.hostname"),
            "站点键运行时取 location.hostname（与 Android 孪生同口径）"
        );
        assert!(
            script.matches("const seed = aegisCanvasSeed();").count() >= 3,
            "三通道噪声必须全部消费站点键"
        );
        // 旧的会话级直取形态必须消失
        assert!(
            !script.contains("__AEGIS_SESSION_SEED.slice(0, 8)"),
            "canvas 不得再直接消费会话级种子切片（跨站关联面）"
        );
        // hardwareConcurrency 随机化仍由会话种子驱动（低熵值非关联向量，保留）
        assert!(script.contains("__AEGIS_SESSION_SEED.slice(8, 16)"));
    }

    #[test]
    fn canvas_noise_perturbs_multiple_channels() {
        // RS-215：R/G/B 三通道扰动——单 R 通道噪声形态与 Android 孪生
        //（AD-175 多通道口径）不一致，跨端噪声形态差异本身即指纹差异面
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        assert!(
            script.contains("imageData.data[i + 1]"),
            "G 通道必须参与扰动"
        );
        assert!(
            script.contains("imageData.data[i + 2]"),
            "B 通道必须参与扰动"
        );
        // alpha（i + 3）不动——透明度变化视觉可察
        assert!(!script.contains("imageData.data[i + 3]"));
    }

    // —— RS-249/250/257 回归（审计 2026-10-01） ——

    #[test]
    fn canvas_noise_is_per_pixel_not_constant_offset() {
        // RS-249：噪声必须逐像素混合——(seed+i)%N 在 i+=4 步进下每通道
        // 全图只取常量偏置（减法即还原）。三通道不同常数 Math.imul 混合
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        for (channel, k) in [(0usize, "0x9E3779B1"), (1, "0x85EBCA6B"), (2, "0x27D4EB2F")] {
            let form = if channel == 0 {
                "imageData.data[i]".to_string()
            } else {
                format!("imageData.data[i + {channel}]")
            };
            let expected = format!("Math.imul(i, {k})");
            let line = script
                .lines()
                .find(|l| l.contains(&form) && l.contains("seed ^"))
                .unwrap_or_else(|| panic!("通道 {channel} 缺少逐像素混合形态"));
            assert!(
                line.contains(&expected),
                "通道 {channel} 必须用常数 {k} 混合：{line}"
            );
        }
        // 旧的常量偏置形态必须消失
        assert!(
            !script.contains("(seed + i) % 2"),
            "(seed+i)%N 常量偏置形态必须移除"
        );
        // 三通道噪声形态在全部三个读取通道（toDataURL/toBlob/convertToBlob）一致
        assert_eq!(script.matches("Math.imul(i, 0x9E3779B1)").count(), 3);
    }

    #[test]
    fn hardware_concurrency_replaced_at_prototype_level() {
        // RS-250：hardwareConcurrency 必须原型级 getter 替换——实例遮蔽可经
        // 原型 descriptor 的原 getter 直取原值
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        assert!(
            script.contains(
                "Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency')"
            ),
            "原型 descriptor 探测"
        );
        assert!(
            script.contains("Object.defineProperty(Navigator.prototype, 'hardwareConcurrency'"),
            "原型级替换"
        );
        assert!(
            !script.contains("defineProperty(navigator, 'hardwareConcurrency'"),
            "实例遮蔽形态必须移除"
        );
        // 保留原 descriptor 属性
        assert!(script.contains("enumerable: oHC.enumerable"));
        assert!(script.contains("configurable: oHC.configurable"));
        // 种子切片消费保留（低熵值非关联向量）
        assert!(script.contains("__AEGIS_SESSION_SEED.slice(8, 16)"));
    }

    #[test]
    fn canvas_seed_uses_public_suffix_aware_etld1() {
        // RS-257：eTLD+1 提取带公共后缀表——a.co.uk 与 b.co.uk 此前共享
        // 站点键（最后两标签同为 co.uk，跨站关联面）
        let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
        assert!(
            script.contains("AEGIS_PUBLIC_SUFFIXES"),
            "最小公共后缀表必须存在"
        );
        assert!(script.contains("'co.uk': 1"), "co.uk 在表中");
        assert!(script.contains("'github.io': 1"), "github.io 在表中");
        assert!(
            script.contains("return parts.slice(-3).join('.');"),
            "公共后缀命中时升级到三标签"
        );
        assert!(
            script.contains("function aegisEtldPlus1("),
            "eTLD+1 提取单源函数"
        );
    }
}

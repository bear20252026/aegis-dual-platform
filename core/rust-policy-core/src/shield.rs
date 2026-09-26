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
    pub fn seed_hex(&self) -> String {
        self.seed.iter().map(|b| format!("{b:02x}")).collect()
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
    pub fn inject_script(&self) -> String {
        let hex = self.seed_hex();
        format!(
            r#"
// Aegis FingerprintShield — 每会话确定性噪声种子（闭包封装——不进全局作用域）
(function() {{
  const __AEGIS_SESSION_SEED = '{hex}';

// Canvas 噪声（每个像素 +1/-1 随机偏移——视觉不可察觉）
// RS-025（审计 2026-09-24）：噪声施加在**离屏副本**上——此前就地
// putImageData 把噪声写回原画布，页面双读（toDataURL 前后各 getImageData
// 一次）即可检测像素漂移
(function() {{
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {{
    try {{
      const ctx = this.getContext('2d');
      if (ctx) {{
        const off = document.createElement('canvas');
        off.width = this.width;
        off.height = this.height;
        const octx = off.getContext('2d');
        octx.drawImage(this, 0, 0);
        const imageData = octx.getImageData(0, 0, off.width, off.height);
        const seed = parseInt(__AEGIS_SESSION_SEED.slice(0, 8), 16);
        for (let i = 0; i < imageData.data.length; i += 4) {{
          imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1;
        }}
        octx.putImageData(imageData, 0, 0);
        return origToDataURL.apply(off, arguments);
      }}
    }} catch (e) {{}}
    return origToDataURL.apply(this, arguments);
  }};
  if (window[Symbol.for('aegis.proxy.register.v1')]) window[Symbol.for('aegis.proxy.register.v1')](HTMLCanvasElement.prototype.toDataURL, origToDataURL);
}})();

// RS-082（审计 2026-09-25）：toBlob 是 canvas 读取的第二通道——仅覆盖
// toDataURL 时页面走 toBlob 拿到无噪声原图。同型离屏副本 + 噪声
(function() {{
  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
    try {{
      const ctx = this.getContext('2d');
      if (ctx) {{
        const off = document.createElement('canvas');
        off.width = this.width;
        off.height = this.height;
        const octx = off.getContext('2d');
        octx.drawImage(this, 0, 0);
        const imageData = octx.getImageData(0, 0, off.width, off.height);
        const seed = parseInt(__AEGIS_SESSION_SEED.slice(0, 8), 16);
        for (let i = 0; i < imageData.data.length; i += 4) {{
          imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1;
        }}
        octx.putImageData(imageData, 0, 0);
        return origToBlob.call(off, callback, type, quality);
      }}
    }} catch (e) {{}}
    return origToBlob.call(this, callback, type, quality);
  }};
  if (window[Symbol.for('aegis.proxy.register.v1')]) window[Symbol.for('aegis.proxy.register.v1')](HTMLCanvasElement.prototype.toBlob, origToBlob);
}})();

// RS-082：OffscreenCanvas.convertToBlob 是 worker 侧第三通道——同型防护
(function() {{
  if (typeof OffscreenCanvas === 'undefined') return;
  const origConvert = OffscreenCanvas.prototype.convertToBlob;
  OffscreenCanvas.prototype.convertToBlob = function(options) {{
    try {{
      const ctx = this.getContext('2d');
      if (ctx) {{
        const off = new OffscreenCanvas(this.width, this.height);
        const octx = off.getContext('2d');
        octx.drawImage(this, 0, 0);
        const imageData = octx.getImageData(0, 0, off.width, off.height);
        const seed = parseInt(__AEGIS_SESSION_SEED.slice(0, 8), 16);
        for (let i = 0; i < imageData.data.length; i += 4) {{
          imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1;
        }}
        octx.putImageData(imageData, 0, 0);
        return origConvert.call(off, options);
      }}
    }} catch (e) {{}}
    return origConvert.call(this, options);
  }};
  if (window[Symbol.for('aegis.proxy.register.v1')]) window[Symbol.for('aegis.proxy.register.v1')](OffscreenCanvas.prototype.convertToBlob, origConvert);
}})();

// 音频指纹噪声由 PerSiteSeed（RS-028）负责——按站点隔离，不在此模块重复

// hardwareConcurrency 随机化（2-8 核）
(function() {{
  const seed = parseInt(__AEGIS_SESSION_SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => 2 + (seed % 7)
  }});
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
        // RS-081：seed_bytes 与 seed_hex 同源一致（管线阶段消费契约）
        let seed = [7u8; 32];
        let s = FingerprintShield::from_seed(seed);
        assert_eq!(s.seed_bytes(), seed);
        let hex_from_bytes: String = s.seed_bytes().iter().map(|b| format!("{b:02x}")).collect();
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
}

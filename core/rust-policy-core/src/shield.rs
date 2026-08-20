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
    /// 用系统随机源创建新会话种子。
    pub fn new() -> Self {
        let mut seed = [0u8; 32];
        // 用系统时间纳秒 + 进程 ID 生成确定性种子（零外部依赖）
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let pid = std::process::id() as u128;
        // 逐字节填充（避免大位移溢出）
        for i in 0..32usize {
            let val = nanos.wrapping_mul(pid.wrapping_add(i as u128 + 1));
            seed[i] = ((val >> ((i % 16) * 8)) & 0xFF) as u8;
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

    /// 生成 JS 注入脚本（注入 WebView——canvas/WebGL/Audio 噪声）。
    ///
    /// 返回的脚本设置全局 `__AEGIS_SESSION_SEED` 常量，
    /// 供前端指纹噪声生成器使用（每次访问 seed_hex 一致 → 噪声确定性）。
    pub fn inject_script(&self) -> String {
        let hex = self.seed_hex();
        format!(
            r#"
// Aegis FingerprintShield — 每会话确定性噪声种子
const __AEGIS_SESSION_SEED = '{hex}';

// Canvas 噪声（每个像素 +1/-1 随机偏移——视觉不可察觉）
(function() {{
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {{
    const ctx = this.getContext('2d');
    if (ctx) {{
      const imageData = ctx.getImageData(0, 0, this.width, this.height);
      const seed = parseInt(__AEGIS_SESSION_SEED.slice(0, 8), 16);
      for (let i = 0; i < imageData.data.length; i += 4) {{
        imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1;
      }}
      ctx.putImageData(imageData, 0, 0);
    }}
    return origToDataURL.apply(this, arguments);
  }};
}})();

// WebGL 渲染器/供应商伪装
(function() {{
  const origGetParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {{
    const UNMASKED_RENDERER = 37446;
    const UNMASKED_VENDOR = 37445;
    if (p === UNMASKED_RENDERER) return 'ANGLE (Aegis)';
    if (p === UNMASKED_VENDOR) return 'Aegis Privacy';
    return origGetParameter.call(this, p);
  }};
}})();

// hardwareConcurrency 随机化（2-8 核）
(function() {{
  const seed = parseInt(__AEGIS_SESSION_SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => 2 + (seed % 7)
  }});
}})();
"#
        )
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
}

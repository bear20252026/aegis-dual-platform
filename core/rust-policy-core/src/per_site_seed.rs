// 由账号2生成
//! PerSiteSeed（参照 Brave Browser per-site per-storage 种子机制）。
//!
//! 从会话种子 + eTLD+1 域名派生每个站点独立的种子，
//! 确保：
//! - 同一站点内指纹一致（会话内稳定）
//! - 不同站点指纹不同（防跨站关联）
//! - 新会话 = 新指纹（防跨会话追踪）
//!
//! 原始版权声明：
//!   Brave Browser fingerprinting protections by Brave Software
//!   Licensed under MPL-2.0
//!   https://github.com/brave/brave-browser/wiki/Fingerprinting-Protections
//!
//! 核心设计（Brave 原文）：
//!   "Randomization values are derived from a seed that changes per session,
//!    per site (eTLD+1) and per storage area. Third party frames and script
//!    share the seed value of the top level, eTLD+1 domain. This approach is
//!    especially useful in fingerprinters that hash together a large number
//!    of semi-identifiers into a single identifier, since randomizing just
//!    one value 'poisons' the entire fingerprint."
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：与 FingerprintShield/LetterboxShield 管道独立组合。

use std::fmt;

/// PerSiteSeed — 从会话种子 + 域名派生每站点独立种子。
///
/// 使用简单但确定性的哈希（无外部依赖），
/// 保证同一 (session_seed, eTLD+1) 对始终产生相同站点种子。
pub struct PerSiteSeed {
    session_seed: [u8; 32],
}

impl fmt::Debug for PerSiteSeed {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "PerSiteSeed(session=***hidden***)")
    }
}

impl PerSiteSeed {
    /// 从会话种子创建 per-site 种子生成器。
    pub fn new(session_seed: [u8; 32]) -> Self {
        Self { session_seed }
    }

    /// 为指定 eTLD+1 域名派生 16 字节站点种子。
    ///
    /// 使用 SipHash 变体（简化版，零依赖）：
    /// 将 session_seed 与 domain 字节逐字节混合，
    /// 产生确定性但不可预测的站点种子。
    pub fn derive(&self, domain: &str) -> [u8; 16] {
        let mut site_seed = [0u8; 16];
        let domain_bytes = domain.as_bytes();

        // SipHash-like 混合：session_seed 与 domain 逐字节折叠
        for (i, byte) in site_seed.iter_mut().enumerate() {
            let mut acc = self.session_seed[i % 32] as u32;
            for (j, &db) in domain_bytes.iter().enumerate() {
                // 乘法混叠 + 异或折叠
                acc = acc
                    .wrapping_mul(31)
                    .wrapping_add(db as u32)
                    .wrapping_add(j as u32);
                acc ^= acc >> 16;
            }
            *byte = (acc & 0xFF) as u8;
        }
        site_seed
    }

    /// 为指定域名生成 per-site 种子的十六进制表示。
    pub fn derive_hex(&self, domain: &str) -> String {
        self.derive(domain)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    }

    /// 生成 per-site 种子注入 JS 脚本。
    ///
    /// 返回的 JS 代码：
    /// 1. 从页面 URL 提取 eTLD+1 域名
    /// 2. 用 session_seed + domain 派生 per-site 种子
    /// 3. 设置 `__AEGIS_SITE_SEED` 全局常量
    ///
    /// 后续的指纹噪声模块读取 `__AEGIS_SITE_SEED` 而非 `__AEGIS_SESSION_SEED`，
    /// 实现 per-site 隔离。
    pub fn inject_script(&self, session_seed_hex: &str) -> String {
        format!(
            r#"
// Aegis PerSiteSeed — per-site 独立种子（参照 Brave Browser）
// 原始设计：Brave Software (MPL-2.0)
// 从 __AEGIS_SESSION_SEED + eTLD+1 域名派生每站点独立种子
// 确保：同站点一致 + 跨站点隔离 + 跨会话刷新
(function() {{
  function getETLD1(hostname) {{
    // 简化 eTLD+1 提取：取最后两段（www.example.com → example.com）
    // 生产环境应使用 Public Suffix List
    var parts = hostname.split('.');
    if (parts.length <= 2) return hostname;
    return parts.slice(-2).join('.');
  }}

  function deriveSeed(sessionHex, domain) {{
    // SipHash-like 混合（与 Rust PerSiteSeed::derive 一致）
    var result = '';
    for (var i = 0; i < 16; i++) {{
      var acc = parseInt(sessionHex.slice((i % 32) * 2, (i % 32) * 2 + 2), 16);
      for (var j = 0; j < domain.length; j++) {{
        acc = (Math.imul(acc, 31) + domain.charCodeAt(j) + j) | 0;
        acc ^= (acc >>> 16);
      }}
      result += ('0' + (acc & 0xFF).toString(16)).slice(-2);
    }}
    return result;
  }}

  var domain = getETLD1(location.hostname);
  var siteSeed = deriveSeed('{session_seed_hex}', domain);
  // __AEGIS_SITE_SEED 供后续指纹噪声模块使用
  Object.defineProperty(window, '__AEGIS_SITE_SEED', {{
    value: siteSeed,
    writable: false,
    configurable: false
  }});
}})();
"#
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_seed() -> [u8; 32] {
        [42u8; 32]
    }

    #[test]
    fn same_domain_same_seed() {
        let pss = PerSiteSeed::new(test_seed());
        assert_eq!(pss.derive("example.com"), pss.derive("example.com"));
    }

    #[test]
    fn different_domain_different_seed() {
        let pss = PerSiteSeed::new(test_seed());
        assert_ne!(pss.derive("example.com"), pss.derive("evil.com"));
    }

    #[test]
    fn different_session_different_seed() {
        let a = PerSiteSeed::new([1u8; 32]);
        let b = PerSiteSeed::new([2u8; 32]);
        assert_ne!(a.derive("example.com"), b.derive("example.com"));
    }

    #[test]
    fn hex_is_32_chars() {
        let pss = PerSiteSeed::new(test_seed());
        assert_eq!(pss.derive_hex("example.com").len(), 32);
    }

    #[test]
    fn script_contains_site_seed_marker() {
        let pss = PerSiteSeed::new(test_seed());
        let script = pss.inject_script(
            &pss.session_seed
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect::<String>(),
        );
        assert!(script.contains("__AEGIS_SITE_SEED"));
        assert!(script.contains("getETLD1"));
        assert!(script.contains("deriveSeed"));
    }
}

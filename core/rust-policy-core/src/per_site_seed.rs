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
//! 安全修复（相对初版）：
//! - 派生改用 SHA-256（域间密钥分离：多站点种子不再可线性逆推会话种子——
//!   初版自制混合 acc*31+byte 的种子可被暴力推算）；
//! - 注入脚本**不携带会话种子原文**、**不暴露全局 `__AEGIS_SITE_SEED`**
//!   （初版把会话种子内嵌进每个站点且以只读全局暴露——页面按名即可读取，
//!   等于主动发放的跨站标识符）。站点种子按域派生后仅存在于闭包内。
//!
//! 可拆卸：不依赖 UI/策略引擎。可拼接：与 FingerprintShield 独立组合。

use sha2::{Digest, Sha256};
use std::fmt;

/// PerSiteSeed — 从会话种子 + 域名派生每站点独立种子。
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
    /// SHA-256(session_seed ‖ "per-site-seed:v2" ‖ domain) 前 16 字节——
    /// 确定性（同输入同输出）、域间密钥分离（单域种子不可逆推会话种子
    /// 或其它域的种子）。
    pub fn derive(&self, domain: &str) -> [u8; 16] {
        let mut hasher = Sha256::new();
        hasher.update(self.session_seed);
        hasher.update(b"aegis:per-site-seed:v2:");
        hasher.update(domain.as_bytes());
        let digest = hasher.finalize();
        let mut site_seed = [0u8; 16];
        site_seed.copy_from_slice(&digest[..16]);
        site_seed
    }

    /// 为指定域名生成 per-site 种子的十六进制表示。
    pub fn derive_hex(&self, domain: &str) -> String {
        self.derive(domain)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    }

    /// 生成指定域名的 per-site 种子注入 JS 脚本。
    ///
    /// - 调用方传入该 WebView 顶层文档的域名（宿主已知，页面不可伪造参数）；
    /// - 种子在 Rust 侧派生——脚本内嵌的**只有该站自己的种子**，不含会话
    ///   种子原文；
    /// - 种子只存在于闭包局部——页面无法按名读取（也不再注册全局常量）。
    pub fn inject_script(&self, domain: &str) -> String {
        let site_seed_hex = self.derive_hex(domain);
        format!(
            r#"
// Aegis PerSiteSeed — per-site 独立种子（参照 Brave Browser，MPL-2.0）
// 同站点一致 + 跨站点隔离 + 跨会话刷新；种子闭包封装（不进全局作用域）
(function() {{
  const __AEGIS_SITE_SEED = '{site_seed_hex}';
  // 供同脚本内噪声模块确定性取用；不挂载到 window
  return __AEGIS_SITE_SEED;
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
    fn script_embeds_site_seed_but_not_session_seed() {
        let pss = PerSiteSeed::new(test_seed());
        let session_hex = pss
            .session_seed
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        let script = pss.inject_script("example.com");
        assert!(script.contains("__AEGIS_SITE_SEED"));
        // 会话种子原文绝不内嵌；站点种子不注册全局属性
        assert!(!script.contains(&session_hex));
        assert!(!script.contains("Object.defineProperty"));
    }

    #[test]
    fn seed_is_sha256_derived() {
        // 域密钥分离：改变域名只改变该域种子，且输出与 SHA-256 截断一致
        let pss = PerSiteSeed::new(test_seed());
        let mut hasher = Sha256::new();
        hasher.update(test_seed());
        hasher.update(b"aegis:per-site-seed:v2:example.com");
        let expected = hasher.finalize();
        assert_eq!(&pss.derive("example.com")[..], &expected[..16]);
    }
}

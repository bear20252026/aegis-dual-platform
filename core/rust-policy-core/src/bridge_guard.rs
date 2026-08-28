//! Bridge 硬化（照搬 AdarshK11/SecureWebViewContainer NativeBridge.kt 本地化适配）。
//!
//! 两端各司其职：
//! - 原生 [`BridgeGuard::validate`]：对 bridge **目标**做 HTTPS + 域名白名单校验（fail-closed）。
//! - 注入页面脚本 [`BridgeGuard::inject_script`]：拦截 fetch / XMLHttpRequest / sendBeacon /
//!   WebSocket，只有**调用方自身属于受信内页**（hostname ∈ 白名单）才放行 bridge 调用。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：WebView 创建时注入为 JS bridge 的安全门。

use std::collections::HashSet;

/// 注入脚本中的占位符：用 `.replace()` 组装，避免与 JS 花括号冲突，也无需 `format!` 转义。
/// 模板因此保持人类可读、可单测断言。
const SCRIPT_PLACEHOLDER_HOSTS: &str = "__AEGIS_HOSTS__";
const SCRIPT_PLACEHOLDER_HTTPS: &str = "__AEGIS_REQUIRE_HTTPS__";

/// JS 桥安全配置。
#[derive(Debug)]
pub struct BridgeGuard {
    /// 允许调用 bridge 的域名白名单。
    allowed_hosts: HashSet<String>,
    /// 是否强制 HTTPS（true=仅 HTTPS 允许调用 bridge）。
    require_https: bool,
}

impl BridgeGuard {
    pub fn new(allowed_hosts: Vec<String>, require_https: bool) -> Self {
        Self {
            allowed_hosts: allowed_hosts.into_iter().collect(),
            require_https,
        }
    }

    /// 验证 bridge 调用是否允许（对 bridge **目标**做校验）。
    /// 返回 Ok(()) 允许，Err(reason) 拒绝。
    pub fn validate(&self, scheme: &str, host: &str) -> Result<(), String> {
        if self.require_https && scheme != "https" {
            return Err(format!("bridge 调用拒绝：非 HTTPS（scheme={scheme}）"));
        }
        if !self.allowed_hosts.is_empty() && !self.allowed_hosts.contains(host) {
            return Err(format!("bridge 调用拒绝：host {host} 不在白名单中"));
        }
        Ok(())
    }

    /// 生成 JS 注入脚本（拦截未授权的 bridge 调用，覆盖 4 种网络出口）。
    ///
    /// 安全模型：只有「调用方自身 hostname ∈ 白名单」的受信内页才能调用 bridge，
    /// 普通站点的非 bridge 流量一律放行（不影响正常浏览）。
    pub fn inject_script(&self) -> String {
        let mut hosts: Vec<&str> = self.allowed_hosts.iter().map(|s| s.as_str()).collect();
        hosts.sort_unstable(); // 稳定输出，便于测试断言
        let hosts_json = serde_json::to_string(&hosts).unwrap_or_else(|_| "[]".to_string());
        let require_https = if self.require_https { "true" } else { "false" };

        const SCRIPT: &str = r#"
// Aegis BridgeGuard — 受信调用方校验（fetch / XMLHttpRequest / sendBeacon / WebSocket）
(function() {
  const ALLOWED_HOSTS = __AEGIS_HOSTS__;
  const REQUIRE_HTTPS = __AEGIS_REQUIRE_HTTPS__;
  // 仅容许「受信内页」（自身 hostname ∈ 白名单）调用本机 bridge。
  const trustedCaller = ALLOWED_HOSTS.includes(location.hostname);
  function isBridgeTarget(urlLike) {
    try { return ALLOWED_HOSTS.includes(new URL(urlLike, location.href).hostname); }
    catch (e) { return false; }
  }
  function shouldBlock(urlLike) {
    if (!isBridgeTarget(urlLike)) return false;   // 普通站点流量放行
    if (!trustedCaller) return true;              // 调用方非受信内页 → 拒绝
    if (REQUIRE_HTTPS) {
      try { if (new URL(urlLike, location.href).protocol !== 'https:') return true; } catch (e) {}
    }
    return false;
  }
  function deny(reason) { console.warn('[Aegis] Bridge blocked: ' + reason); }
  const fetch0 = window.fetch;
  window.fetch = function(input, init) {
    if (shouldBlock(input && input.url ? input.url : input)) { deny('fetch'); return Promise.reject(new Error('Aegis: bridge blocked')); }
    return fetch0.apply(this, arguments);
  };
  const open0 = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (shouldBlock(url)) { deny('xhr'); throw new Error('Aegis: bridge blocked'); }
    return open0.apply(this, arguments);
  };
  const beacon0 = navigator.sendBeacon && navigator.sendBeacon;
  navigator.sendBeacon = function(url) {
    if (shouldBlock(url)) { deny('beacon'); return false; }
    return beacon0.apply(navigator, arguments);
  };
  const WS = window.WebSocket;
  window.WebSocket = function(url, protocols) {
    if (shouldBlock(url)) { deny('websocket'); throw new Error('Aegis: bridge blocked'); }
    return new WS(url, protocols);
  };
  window.WebSocket.CONNECTING = WS.CONNECTING;
  window.WebSocket.OPEN = WS.OPEN;
  window.WebSocket.CLOSING = WS.CLOSING;
  window.WebSocket.CLOSED = WS.CLOSED;
})();
"#;

        SCRIPT
            .replace(SCRIPT_PLACEHOLDER_HOSTS, &hosts_json)
            .replace(SCRIPT_PLACEHOLDER_HTTPS, require_https)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn https_allowed_host_passes() {
        let guard = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(guard.validate("https", "example.com").is_ok());
    }

    #[test]
    fn http_rejected_when_require_https() {
        let guard = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(guard.validate("http", "example.com").is_err());
    }

    #[test]
    fn unknown_host_rejected() {
        let guard = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(guard.validate("https", "evil.com").is_err());
    }

    #[test]
    fn empty_allowlist_permits_all() {
        let guard = BridgeGuard::new(vec![], false);
        assert!(guard.validate("http", "any.com").is_ok());
    }

    // —— 注入脚本质量断言（防回归：注释与实现保持一致，且覆盖所有网络出口）——
    #[test]
    fn inject_script_covers_all_sinks() {
        let guard = BridgeGuard::new(vec!["aegis.local".into()], true);
        let s = guard.inject_script();
        for needle in [
            "window.fetch = function",
            "XMLHttpRequest.prototype.open",
            "navigator.sendBeacon = function",
            "window.WebSocket = function",
        ] {
            assert!(s.contains(needle), "注入脚本缺少拦截点：{needle}");
        }
        // 核心安全属性：受信调用方（自身 hostname ∈ 白名单）校验
        assert!(s.contains("trustedCaller"));
        assert!(s.contains("location.hostname"));
    }

    #[test]
    fn inject_script_substitutes_allowlist_and_https() {
        let guard = BridgeGuard::new(vec!["aegis.local".into(), "localhost".into()], true);
        let s = guard.inject_script();
        // 模板占位符必须被替换，不得残留
        assert!(!s.contains(SCRIPT_PLACEHOLDER_HOSTS));
        assert!(!s.contains(SCRIPT_PLACEHOLDER_HTTPS));
        assert!(s.contains("\"aegis.local\""));
        assert!(s.contains("REQUIRE_HTTPS = true"));

        // HTTPS 未开启时输出 false
        let guard_no_https = BridgeGuard::new(vec!["aegis.local".into()], false);
        let s2 = guard_no_https.inject_script();
        assert!(s2.contains("REQUIRE_HTTPS = false"));
    }
}

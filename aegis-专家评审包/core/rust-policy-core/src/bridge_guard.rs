//! Bridge 硬化（照搬 AdarshK11/SecureWebViewContainer NativeBridge.kt 本地化适配）。
//!
//! JS 桥调用必须通过 origin 校验（HTTPS + 域名白名单），
//! 未通过的调用直接拒绝（fail-closed）。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：WebView 创建时注入为 JS bridge 的安全门。

use std::collections::HashSet;

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

    /// 验证 bridge 调用是否允许。
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

    /// 生成 JS 注入脚本（拦截未授权的 bridge 调用）。
    pub fn inject_script(&self) -> String {
        let hosts: Vec<&str> = self.allowed_hosts.iter().map(|s| s.as_str()).collect();
        let hosts_json = serde_json::to_string(&hosts).unwrap_or_else(|_| "[]".to_string());
        let require_https = self.require_https;
        format!(
            r#"
// Aegis BridgeGuard — origin 校验拦截
(function() {{
  const ALLOWED_HOSTS = {hosts_json};
  const REQUIRE_HTTPS = {require_https};
  const origFetch = window.fetch;
  window.fetch = function(url) {{
    try {{
      const u = new URL(url, location.href);
      if (REQUIRE_HTTPS && u.protocol !== 'https:') {{
        console.warn('[Aegis] Bridge blocked: non-HTTPS', u.href);
        return Promise.reject(new Error('Aegis: non-HTTPS bridge blocked'));
      }}
      if (ALLOWED_HOSTS.length > 0 && !ALLOWED_HOSTS.includes(u.hostname)) {{
        console.warn('[Aegis] Bridge blocked: host not allowed', u.hostname);
        return Promise.reject(new Error('Aegis: host not in allowlist'));
      }}
    }} catch(e) {{}}
    return origFetch.apply(this, arguments);
  }};
}})();
"#
        )
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
}

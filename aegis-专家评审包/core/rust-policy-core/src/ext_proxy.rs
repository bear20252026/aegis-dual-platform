// 由账号2生成
//! ExtProxy（参照 Helium Browser 匿名扩展下载代理）。
//!
//! 拦截 Chrome Web Store 的扩展下载/更新请求，
//! 通过可配置的匿名代理端点转发，防止 Google 追踪用户的扩展安装行为。
//!
//! 原始版权声明：
//!   Helium Browser by imputnet (GPL-3.0)
//!   https://github.com/imputnet/helium
//!
//! 原始设计（Helium README）：
//!   "All requests to Chrome Web Store are anonymized via Helium services,
//!    so Google can't track your extension downloads/updates."
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 Request Interceptor 管线中作为独立阶段调用。

use std::fmt;

/// 匿名代理端点配置。
#[derive(Debug, Clone)]
pub struct ExtProxyConfig {
    /// 代理端点 URL（空字符串 = 禁用代理）。
    pub proxy_endpoint: String,
    /// 是否拦截扩展下载请求。
    pub intercept_downloads: bool,
    /// 是否拦截扩展更新检查。
    pub intercept_updates: bool,
}

impl Default for ExtProxyConfig {
    fn default() -> Self {
        Self {
            // 默认禁用——需要用户配置代理端点
            proxy_endpoint: String::new(),
            intercept_downloads: true,
            intercept_updates: true,
        }
    }
}

/// ExtProxy — 匿名扩展下载代理。
///
/// 拦截 Chrome Web Store 请求并通过匿名代理转发，
/// 防止 Google 追踪用户的扩展安装行为。
pub struct ExtProxy {
    config: ExtProxyConfig,
}

impl fmt::Debug for ExtProxy {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "ExtProxy(endpoint={}, downloads={}, updates={})",
            if self.config.proxy_endpoint.is_empty() {
                "disabled"
            } else {
                "configured"
            },
            self.config.intercept_downloads,
            self.config.intercept_updates
        )
    }
}

impl ExtProxy {
    /// 用默认配置创建（代理禁用，需用户配置端点）。
    pub fn new() -> Self {
        Self {
            config: ExtProxyConfig::default(),
        }
    }

    /// 用自定义代理端点创建。
    pub fn with_endpoint(endpoint: &str) -> Self {
        Self {
            config: ExtProxyConfig {
                proxy_endpoint: endpoint.to_string(),
                ..ExtProxyConfig::default()
            },
        }
    }

    /// 用自定义配置创建。
    pub fn with_config(config: ExtProxyConfig) -> Self {
        Self { config }
    }

    /// 生成匿名扩展代理 JS 注入脚本。
    ///
    /// 拦截：
    /// - Chrome Web Store 扩展下载请求（clients2.google.com/service/update2/crx）
    /// - Chrome Web Store 扩展更新检查（clients2.google.com/service/update2/json）
    ///
    /// 如果 proxy_endpoint 为空，脚本仅注册拦截逻辑但不转发（观察模式）。
    pub fn inject_script(&self) -> String {
        let endpoint = &self.config.proxy_endpoint;
        let intercept_dl = self.config.intercept_downloads;
        let intercept_up = self.config.intercept_updates;
        format!(
            r#"
// Aegis ExtProxy — 匿名扩展下载代理（参照 Helium Browser）
// 原始设计：imputnet/helium (GPL-3.0)
// 拦截 Chrome Web Store 请求，通过匿名代理转发
(function() {{
  var PROXY_ENDPOINT = '{endpoint}';
  var INTERCEPT_DOWNLOADS = {intercept_dl};
  var INTERCEPT_UPDATES = {intercept_up};

  // Chrome Web Store 匹配模式
  var CWS_DOWNLOAD_PATTERN = /^https?:\/\/clients2\.google\.com\/service\/update2\/crx/i;
  var CWS_UPDATE_PATTERN = /^https?:\/\/clients2\.google\.com\/service\/update2\/json/i;

  function shouldIntercept(url) {{
    if (INTERCEPT_DOWNLOADS && CWS_DOWNLOAD_PATTERN.test(url)) return true;
    if (INTERCEPT_UPDATES && CWS_UPDATE_PATTERN.test(url)) return true;
    return false;
  }}

  function proxyUrl(originalUrl) {{
    if (!PROXY_ENDPOINT) return originalUrl; // 无代理端点，直连
    // 将原始 URL 作为参数传递给代理端点
    return PROXY_ENDPOINT + '?url=' + encodeURIComponent(originalUrl);
  }}

  // 拦截 fetch 请求
  try {{
    var origFetch = window.fetch;
    window.fetch = function(input, init) {{
      var url = typeof input === 'string' ? input : (input instanceof Request ? input.url : '');
      if (shouldIntercept(url)) {{
        var proxied = proxyUrl(url);
        if (typeof input === 'string') {{
          input = proxied;
        }} else if (input instanceof Request) {{
          input = new Request(proxied, input);
        }}
      }}
      return origFetch.call(this, input, init);
    }};
  }} catch(e) {{}}

  // 拦截 XMLHttpRequest.open
  try {{
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {{
      if (shouldIntercept(url)) {{
        arguments[1] = proxyUrl(url);
      }}
      return origOpen.apply(this, arguments);
    }};
  }} catch(e) {{}}
}})();
"#
        )
    }
}

impl Default for ExtProxy {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_has_empty_endpoint() {
        let config = ExtProxyConfig::default();
        assert!(config.proxy_endpoint.is_empty());
        assert!(config.intercept_downloads);
        assert!(config.intercept_updates);
    }

    #[test]
    fn script_contains_cws_patterns() {
        let ep = ExtProxy::new();
        let script = ep.inject_script();
        assert!(script.contains("clients2"));
        assert!(script.contains("update2"));
        assert!(script.contains("crx"));
        assert!(script.contains("json"));
    }

    #[test]
    fn script_with_endpoint_configured() {
        let ep = ExtProxy::with_endpoint("https://proxy.example.com/anon");
        let script = ep.inject_script();
        assert!(script.contains("proxy.example.com/anon"));
    }

    #[test]
    fn script_without_endpoint_uses_direct() {
        let ep = ExtProxy::new();
        let script = ep.inject_script();
        assert!(script.contains("return originalUrl"));
    }

    #[test]
    fn debug_format_shows_status() {
        let ep = ExtProxy::new();
        let debug = format!("{:?}", ep);
        assert!(debug.contains("disabled"));
    }
}

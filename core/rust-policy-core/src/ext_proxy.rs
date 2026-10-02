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

/// RS-285（2026-10-02 审计）：endpoint 是否以 http(s):// 前缀开头（ASCII
/// 大小写不敏感）。按字节前缀比较（eq_ignore_ascii_case），不做字符串
/// 切片（避免多字节字符边界 panic）；WHATWG URL scheme 大小写不敏感，
/// `HTTPS://`/`Http://` 是合法端点形态。
fn endpoint_has_http_scheme(endpoint: &str) -> bool {
    ["https://", "http://"].iter().any(|prefix| {
        let bytes = endpoint.as_bytes();
        bytes.len() >= prefix.len() && bytes[..prefix.len()].eq_ignore_ascii_case(prefix.as_bytes())
    })
}

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
    ///
    /// RS-086（审计 2026-09-25）：端点必须为 http(s) URL——此前任意串
    /// 直通注入 JS（`javascript:`/相对路径端点会把扩展流量导向攻击者
    /// 控制的上下文）。非法 scheme fail-closed 退化为空端点（观察模式）。
    /// RS-285（2026-10-02 审计）：scheme 前缀比较改 ASCII 大小写不敏感
    /// ——WHATWG URL scheme 大小写不敏感，`HTTPS://`/`Http://` 端点此前
    /// 被 fail-closed 静默拒绝（合法配置退化禁用）。
    pub fn with_endpoint(endpoint: &str) -> Self {
        let normalized = if endpoint_has_http_scheme(endpoint) {
            endpoint.to_string()
        } else {
            String::new()
        };
        Self {
            config: ExtProxyConfig {
                proxy_endpoint: normalized,
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
        // RS-255（2026-10-01 审计）：scheme 归一防御性再校验——with_endpoint
        // 之外，with_config/直接构造 ExtProxyConfig 可绕过校验携带任意
        // scheme 端点（javascript:/相对路径把扩展流量导向攻击者上下文）。
        // 注入是最后防线：非法端点在此退化空（观察模式），与 RS-086 同口径
        // RS-285（2026-10-02 审计）：比较改 ASCII 大小写不敏感（WHATWG
        // scheme 大小写不敏感，大写/混合形态端点是合法配置）
        let endpoint = if endpoint_has_http_scheme(&self.config.proxy_endpoint) {
            &self.config.proxy_endpoint
        } else {
            ""
        };
        // RS-225（2026-09-26 审计）：端点转义改走 util::js_escape_single_quoted
        // 单源——此前内联 replace 链漏 \n/\r 转义，端点含换行即产出
        // 语法错误脚本
        let endpoint_escaped = crate::util::js_escape_single_quoted(endpoint);
        let intercept_dl = self.config.intercept_downloads;
        let intercept_up = self.config.intercept_updates;
        // RS-242（2026-10-01 审计）：代理注册接口 Symbol 键单源引用
        //（描述串去品牌化——详见 ToStringGuard::REGISTER_SYMBOL）
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
        format!(
            r#"
// Aegis ExtProxy — 匿名扩展下载代理（参照 Helium Browser）
// 原始设计：imputnet/helium (GPL-3.0)
// 拦截 Chrome Web Store 请求，通过匿名代理转发
(function() {{
  // 端点经 JS 字符串转义（含单引号即注入）
  var PROXY_ENDPOINT = '{endpoint_escaped}';
  var INTERCEPT_DOWNLOADS = {intercept_dl};
  var INTERCEPT_UPDATES = {intercept_up};

  // Chrome Web Store 匹配模式
  // RS-087（审计 2026-09-25）：拦截面此前仅 clients2.google.com 一个域名
  // ——扩展下载/更新同样走 googleusercontent 媒体通道与商店站内请求
  var CWS_DOWNLOAD_PATTERN = /^https?:\/\/clients2\.google\.com\/service\/update2\/crx/i;
  var CWS_UPDATE_PATTERN = /^https?:\/\/clients2\.google\.com\/service\/update2\/json/i;
  var CWS_MEDIA_PATTERN = /^https?:\/\/clients2\.googleusercontent\.com\/crx\//i;
  var CWS_STORE_PATTERN = /^https?:\/\/chromewebstore\.google\.com\//i;

  function shouldIntercept(url) {{
    if (INTERCEPT_DOWNLOADS && (CWS_DOWNLOAD_PATTERN.test(url) || CWS_MEDIA_PATTERN.test(url))) return true;
    if (INTERCEPT_UPDATES && (CWS_UPDATE_PATTERN.test(url) || CWS_STORE_PATTERN.test(url))) return true;
    return false;
  }}

  function proxyUrl(originalUrl) {{
    if (!PROXY_ENDPOINT) return originalUrl; // 无代理端点，直连
    // 将原始 URL 作为参数传递给代理端点。
    // RS-226（2026-09-26 审计）：端点自带 query 时用 '&' 拼接——固定
    // 拼 '?url=' 会产出双问号畸形地址（https://p/e?k=1?url=...）
    var joiner = PROXY_ENDPOINT.indexOf('?') >= 0 ? '&' : '?';
    return PROXY_ENDPOINT + joiner + 'url=' + encodeURIComponent(originalUrl);
  }}

  // 拦截 fetch 请求
  try {{
    var origFetch = window.fetch;
    window.fetch = function(input, init) {{
      // RS-280（2026-10-02 审计）：补 URL 对象形态——此前 string/Request
      // 之外的形态（URL 对象）取不到 url，shouldIntercept('') 恒 false，
      // URL 对象请求完整绕过拦截
      var isUrlObj = input instanceof URL;
      var url = typeof input === 'string'
        ? input
        : (input instanceof Request ? input.url : (isUrlObj ? input.href : ''));
      if (shouldIntercept(url)) {{
        var proxied = proxyUrl(url);
        if (typeof input === 'string') {{
          input = proxied;
        }} else if (input instanceof Request) {{
          input = new Request(proxied, input);
        }} else if (isUrlObj) {{
          // RS-280：URL 对象形态以代理串传递（fetch 接受字符串）
          input = proxied;
        }}
      }}
      return origFetch.call(this, input, init);
    }};
  }} catch(e) {{}}

  // 拦截 XMLHttpRequest.open
  // RS-232（2026-09-26 审计）：显式参数转发——arguments[1] 写回赋值
  // 仅非严格模式合法（严格模式下不生效），改显式收集转发
  try {{
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {{
      var rest = Array.prototype.slice.call(arguments, 2);
      if (shouldIntercept(url)) {{
        url = proxyUrl(url);
      }}
      return origOpen.apply(this, [method, url].concat(rest));
    }};
  }} catch(e) {{}}

  // RS-242（2026-10-01 审计）：fetch/open 覆盖注册 ToStringGuard——
  // 未注册时 fetch.toString() 一行暴露包装源码（内含品牌特征）。
  // 注册接口在 ToStringGuard 阶段之后的注入次序下可用；Compatible 模式
  // 无 guard 时为空转（登记口径见 protection_mode RS-256）
  try {{
    var __aegisReg = window[Symbol.for('{reg_sym}')];
    if (__aegisReg) {{
      __aegisReg(window.fetch, origFetch);
      __aegisReg(XMLHttpRequest.prototype.open, origOpen);
    }}
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

    // —— RS-085/086/087 回归（审计 2026-09-25） ——

    #[test]
    fn endpoint_escaping_regression() {
        // RS-085/P29：端点含单引号/反斜杠必须转义——否则逃逸 JS 字符串
        // 字面量注入任意脚本（配置面输入）
        let ep = ExtProxy::with_endpoint("https://proxy.example.com/a'b\\c");
        let script = ep.inject_script();
        assert!(script.contains("a\\'b\\\\c"), "单引号与反斜杠已转义");
        assert!(
            !script.contains("PROXY_ENDPOINT = 'https://proxy.example.com/a'b"),
            "不得残留未转义直拼"
        );
    }

    #[test]
    fn endpoint_scheme_validated() {
        // RS-086：非 http(s) scheme fail-closed 退化禁用（观察模式）
        let bad = ExtProxy::with_endpoint("javascript:alert(1)");
        assert!(
            bad.config.proxy_endpoint.is_empty(),
            "javascript: scheme 拒绝"
        );
        assert!(bad.inject_script().contains("return originalUrl"));
        let relative = ExtProxy::with_endpoint("//evil.com/proxy");
        assert!(
            relative.config.proxy_endpoint.is_empty(),
            "相对路径端点拒绝"
        );
        // 合法 scheme 不受影响
        let ok = ExtProxy::with_endpoint("https://proxy.example.com/anon");
        assert!(!ok.config.proxy_endpoint.is_empty());
    }

    #[test]
    fn interception_surface_covers_all_cws_hosts() {
        // RS-087：拦截面覆盖 google 域 + googleusercontent 媒体通道 + 商店站
        let script = ExtProxy::new().inject_script();
        assert!(script.contains("clients2\\.google\\.com"));
        assert!(
            script.contains("clients2\\.googleusercontent\\.com"),
            "媒体通道"
        );
        assert!(
            script.contains("chromewebstore\\.google\\.com"),
            "商店站内请求"
        );
    }

    // —— RS-225/226/232 回归（审计 2026-09-26） ——

    #[test]
    fn endpoint_escaping_reuses_single_source_with_newlines() {
        // RS-225：端点转义必须走 util::js_escape_single_quoted 单源——
        // 内联 replace 链漏 \n/\r，端点含换行即产出语法错误脚本
        let ep = ExtProxy::with_endpoint("https://proxy.example.com/a'b\nc\\d\re");
        let script = ep.inject_script();
        assert!(
            script.contains("a\\'b\\nc\\\\d\\re"),
            "单引号/换行/回车/反斜杠必须全部转义（单源转义器口径）"
        );
        // 注：scheme 校验（RS-086）放行含换行的 https 端点串——转义器
        // 负责其 JS 字面量安全
    }

    #[test]
    fn proxy_url_joins_query_aware() {
        // RS-226：端点自带 query 时用 '&' 拼接——固定 '?url=' 会产出
        // 双问号畸形地址
        let script =
            ExtProxy::with_endpoint("https://proxy.example.com/anon?key=1").inject_script();
        assert!(
            script.contains("PROXY_ENDPOINT.indexOf('?') >= 0 ? '&' : '?'"),
            "拼接分隔符必须按端点是否含 query 分支"
        );
        assert!(!script.contains("+ '?url=' +"), "固定问号拼接必须移除");
    }

    #[test]
    fn xhr_open_forwards_arguments_explicitly() {
        // RS-232：XHR 拦截不得依赖 `arguments[1] = ...` 写回（仅非严格
        // 模式合法）——必须显式参数转发
        let script = ExtProxy::new().inject_script();
        assert!(
            script.contains("Array.prototype.slice.call(arguments, 2)"),
            "可选参（async/user/password）显式收集"
        );
        assert!(
            script.contains("origOpen.apply(this, [method, url].concat(rest))"),
            "显式转发改写后的 url 与剩余参数"
        );
        assert!(
            !script.contains("arguments[1] ="),
            "arguments 写回形态必须移除（严格模式失效）"
        );
    }

    // —— RS-242/255 回归（审计 2026-10-01） ——

    #[test]
    fn inject_script_defensively_revalidates_endpoint_scheme() {
        // RS-255：with_config/直接构造绕过 with_endpoint 的 scheme 校验——
        // inject_script 是最后防线，非法端点退化空（观察模式）
        let config = ExtProxyConfig {
            proxy_endpoint: "javascript:alert(1)".into(),
            ..ExtProxyConfig::default()
        };
        let script = ExtProxy::with_config(config).inject_script();
        assert!(
            script.contains("PROXY_ENDPOINT = '';"),
            "非法 scheme 端点必须退化空"
        );
        assert!(!script.contains("javascript:"), "非法端点不得进入脚本");
        assert!(script.contains("return originalUrl"), "观察模式直连");
        // 相对路径形态同样退化
        let config = ExtProxyConfig {
            proxy_endpoint: "//evil.com/proxy".into(),
            ..ExtProxyConfig::default()
        };
        assert!(ExtProxy::with_config(config)
            .inject_script()
            .contains("PROXY_ENDPOINT = '';"));
        // 合法端点不受防御性校验影响
        let config = ExtProxyConfig {
            proxy_endpoint: "https://proxy.example.com/anon".into(),
            ..ExtProxyConfig::default()
        };
        let script = ExtProxy::with_config(config).inject_script();
        assert!(script.contains("PROXY_ENDPOINT = 'https://proxy.example.com/anon';"));
    }

    #[test]
    fn fetch_and_xhr_wrappers_registered_with_tostring_guard() {
        // RS-242：fetch/open 覆盖必须注册 ToStringGuard——未注册时
        // fetch.toString() 一行暴露包装源码（内含品牌特征）
        let script = ExtProxy::with_endpoint("https://proxy.example.com/anon").inject_script();
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
        assert_eq!(
            script.matches(&format!("Symbol.for('{reg_sym}')")).count(),
            1,
            "注册接口引用单次（批量注册两包装）"
        );
        assert!(script.contains("__aegisReg(window.fetch, origFetch);"));
        assert!(script.contains("__aegisReg(XMLHttpRequest.prototype.open, origOpen);"));
    }

    // —— RS-280/285 回归（2026-10-02 审计） ——

    #[test]
    fn endpoint_scheme_case_insensitive() {
        // RS-285：scheme 前缀比较 ASCII 大小写不敏感——WHATWG URL scheme
        // 大小写不敏感，大写/混合形态端点是合法配置，此前被静默退化禁用
        let upper = ExtProxy::with_endpoint("HTTPS://proxy.example.com/anon");
        assert!(
            !upper.config.proxy_endpoint.is_empty(),
            "HTTPS:// 大写 scheme 必须接受"
        );
        assert!(upper
            .inject_script()
            .contains("PROXY_ENDPOINT = 'HTTPS://proxy.example.com/anon';"));
        let mixed = ExtProxy::with_endpoint("Http://proxy.example.com/anon");
        assert!(
            !mixed.config.proxy_endpoint.is_empty(),
            "混合大小写 scheme 必须接受"
        );
        // 防御性再校验（inject_script 内）同口径
        let config = ExtProxyConfig {
            proxy_endpoint: "HTTPS://proxy.example.com/anon".into(),
            ..ExtProxyConfig::default()
        };
        assert!(ExtProxy::with_config(config)
            .inject_script()
            .contains("PROXY_ENDPOINT = 'HTTPS://proxy.example.com/anon';"));
        // 非法 scheme 仍拒绝（javascript: 大小写变体 fail-closed）
        let evil = ExtProxy::with_endpoint("JavaScript:alert(1)");
        assert!(
            evil.config.proxy_endpoint.is_empty(),
            "javascript: 大小写变体拒绝"
        );
    }

    #[test]
    fn fetch_url_object_form_intercepted() {
        // RS-280：fetch(URL 对象) 形态此前取不到 url（'' 恒 false 绕过）——
        // 补 URL 对象取 href + 代理串传递
        let script = ExtProxy::with_endpoint("https://proxy.example.com/anon").inject_script();
        assert!(
            script.contains("var isUrlObj = input instanceof URL;"),
            "URL 对象形态必须显式识别"
        );
        assert!(
            script.contains("(isUrlObj ? input.href : '')"),
            "URL 对象取 href 参与拦截判定"
        );
        assert!(
            script.contains("} else if (isUrlObj) {"),
            "命中后 URL 对象形态以代理串传递"
        );
    }
}

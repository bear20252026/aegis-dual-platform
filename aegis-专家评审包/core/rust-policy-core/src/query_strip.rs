// 由账号2生成
//! QueryStripper（参照 LibreWolf / Brave Browser URL 追踪参数剥离）。
//!
//! 从 URL 中移除已知追踪查询参数，防止用户行为被跨站追踪。
//! 剥离列表与 LibreWolf 和 Brave 保持一致。
//!
//! 原始版权声明：
//!   LibreWolf query stripping list (MPL-2.0)
//!   https://gitlab.com/librewolf-community/settings/-/blob/master/librewolf.cfg
//!
//!   Brave query stripping list (MPL-2.0)
//!   https://github.com/brave/brave-core/blob/master/browser/net/brave_site_hacks_network_delegate_helper.cc
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 Request Interceptor 管线中作为独立阶段调用。

use std::fmt;

/// 已知追踪查询参数列表（与 LibreWolf/Brave 一致）。
///
/// 来源：LibreWolf `privacy.query_stripping.strip_list` + Brave 合并列表。
/// 每个参数名都是精确匹配（区分大小写）。
const TRACKING_PARAMS: &[&str] = &[
    // Google Analytics / Ads
    "__hsfp",
    "__hssc",
    "__hstc",
    "__s",
    "_hsenc",
    "_openstat",
    "dclid",
    "gbraid",
    "gclid",
    "hsCtaTracking",
    "mc_eid",
    "ml_subscriber",
    "ml_subscriber_hash",
    "msclkid",
    "wbraid",
    // Facebook
    "fbclid",
    // Instagram
    "igshid",
    // Microsoft / Outlook
    "oft_c",
    "oft_ck",
    "oft_d",
    "oft_id",
    "oft_ids",
    "oft_k",
    "oft_lk",
    "oft_sk",
    // Omniture / Adobe
    "oly_anon_id",
    "oly_enc_id",
    // Other trackers
    "rb_clickid",
    "s_cid",
    "twclid",
    "vero_conv",
    "vero_id",
    "wickedid",
    "yclid",
];

/// QueryStripper — URL 追踪参数剥离器。
///
/// 从 URL 的查询字符串中移除已知追踪参数，
/// 保留非追踪参数（不影响网站功能）。
pub struct QueryStripper {
    params: Vec<String>,
}

impl fmt::Debug for QueryStripper {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "QueryStripper({} params)", self.params.len())
    }
}

impl QueryStripper {
    /// 用默认追踪参数列表创建。
    pub fn new() -> Self {
        Self {
            params: TRACKING_PARAMS.iter().map(|s| s.to_string()).collect(),
        }
    }

    /// 用自定义参数列表创建（可扩展）。
    pub fn with_params(params: Vec<String>) -> Self {
        Self { params }
    }

    /// 从 URL 中剥离追踪参数，返回清理后的 URL。
    ///
    /// 如果 URL 没有查询参数或所有参数都是追踪参数，返回原始 URL。
    /// 保留非追踪参数（如 `?id=123&fbclid=xxx` → `?id=123`）。
    pub fn strip(&self, url: &str) -> String {
        // 分离 scheme://host/path 和 query
        let (base, query_part) = match url.find('?') {
            Some(pos) => (&url[..pos + 1], &url[pos + 1..]),
            None => return url.to_string(),
        };

        // 分离 query 和 fragment
        let (query, fragment) = match query_part.find('#') {
            Some(pos) => (&query_part[..pos], Some(&query_part[pos..])),
            None => (query_part, None),
        };

        // 过滤追踪参数
        let kept: Vec<&str> = query
            .split('&')
            .filter(|param| {
                let key = param.split('=').next().unwrap_or("");
                !self.params.iter().any(|tp| tp == key)
            })
            .collect();

        // 重建 URL
        let mut result = base.to_string();
        if !kept.is_empty() {
            result.push_str(&kept.join("&"));
        }
        if let Some(frag) = fragment {
            // 如果没有保留参数，去掉末尾的 '?'
            if kept.is_empty() {
                result.pop(); // 移除 '?'
            }
            result.push_str(frag);
        } else if kept.is_empty() {
            result.pop(); // 移除 '?'
        }
        result
    }

    /// 生成 JS 注入脚本（在浏览器端拦截 fetch/XHR 请求时剥离参数）。
    pub fn inject_script(&self) -> String {
        let params_json: String = {
            let items: Vec<String> = self.params.iter().map(|p| format!("'{}'", p)).collect();
            format!("[{}]", items.join(","))
        };
        format!(
            r#"
// Aegis QueryStripper — URL 追踪参数剥离（参照 LibreWolf/Brave）
// 原始列表：LibreWolf (MPL-2.0) / Brave Software (MPL-2.0)
(function() {{
  var TRACKING_PARAMS = {params_json};
  function stripParams(url) {{
    try {{
      var u = new URL(url);
      var changed = false;
      TRACKING_PARAMS.forEach(function(p) {{
        if (u.searchParams.has(p)) {{
          u.searchParams.delete(p);
          changed = true;
        }}
      }});
      return changed ? u.toString() : url;
    }} catch(e) {{ return url; }}
  }}

  // 拦截 fetch 请求
  var origFetch = window.fetch;
  window.fetch = function(input, init) {{
    if (typeof input === 'string') {{
      input = stripParams(input);
    }} else if (input instanceof Request) {{
      input = new Request(stripParams(input.url), input);
    }}
    return origFetch.call(this, input, init);
  }};

  // 拦截 XMLHttpRequest.open
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {{
    arguments[1] = stripParams(url);
    return origOpen.apply(this, arguments);
  }};
}})();
"#
        )
    }
}

impl Default for QueryStripper {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strip_removes_tracking_params() {
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/?id=123&fbclid=abc"),
            "https://example.com/?id=123"
        );
    }

    #[test]
    fn strip_preserves_non_tracking_params() {
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/?q=search&page=2"),
            "https://example.com/?q=search&page=2"
        );
    }

    #[test]
    fn strip_removes_all_tracking_params() {
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/?gclid=abc&fbclid=def"),
            "https://example.com/"
        );
    }

    #[test]
    fn strip_preserves_fragment() {
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/?id=1&fbclid=x#section"),
            "https://example.com/?id=1#section"
        );
    }

    #[test]
    fn strip_no_query_returns_original() {
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/path"),
            "https://example.com/path"
        );
    }

    #[test]
    fn script_contains_tracking_params() {
        let qs = QueryStripper::new();
        let script = qs.inject_script();
        assert!(script.contains("fbclid"));
        assert!(script.contains("gclid"));
        assert!(script.contains("stripParams"));
    }

    #[test]
    fn custom_params_work() {
        let qs = QueryStripper::with_params(vec!["custom_track".to_string()]);
        assert_eq!(
            qs.strip("https://example.com/?id=1&custom_track=abc"),
            "https://example.com/?id=1"
        );
    }
}

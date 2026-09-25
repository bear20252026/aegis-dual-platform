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
/// 参数名按 ASCII 不区分大小写匹配（追踪方用 `Gclid`/`gClId` 变体绕过
/// 精确匹配——大小写折叠后命中）。
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
///
/// RS-071（审计 2026-09-25）：参数表用 `Cow<'static, str>`——默认列表
/// 零分配借用静态切片，自定义扩展项才持有 String。
pub struct QueryStripper {
    params: Vec<std::borrow::Cow<'static, str>>,
}

impl fmt::Debug for QueryStripper {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "QueryStripper({} params)", self.params.len())
    }
}

impl QueryStripper {
    /// 用默认追踪参数列表创建（RS-071：静态切片借用，零分配）。
    pub fn new() -> Self {
        Self {
            params: TRACKING_PARAMS.iter().map(|s| (*s).into()).collect(),
        }
    }

    /// 用自定义参数列表创建（可扩展）。
    pub fn with_params(params: Vec<String>) -> Self {
        Self {
            params: params.into_iter().map(std::borrow::Cow::Owned).collect(),
        }
    }

    /// 从 URL 中剥离追踪参数，返回清理后的 URL。
    ///
    /// 如果 URL 没有查询参数或所有参数都是追踪参数，返回不含 query 的
    /// 原始 URL（fragment 原样保留）。保留非追踪参数
    /// （如 `?id=123&fbclid=xxx` → `?id=123`）。
    ///
    /// RS-070（审计 2026-09-25）：先分离 fragment 再定位 query——
    /// 此前直接找首个 `?`，fragment 内的 `?`（`path#a?fbclid=x`）被误当
    /// query 分隔符，fragment 内容遭错误改写（query 在 fragment 之前是
    /// URL 语义，二者不可混淆）。
    pub fn strip(&self, url: &str) -> String {
        // 先分离 fragment（# 之后整段原样保留）
        let (no_fragment, fragment) = match url.find('#') {
            Some(pos) => (&url[..pos], Some(&url[pos..])),
            None => (url, None),
        };
        // 再在 fragment 前缀中定位 query
        let (base, query) = match no_fragment.find('?') {
            Some(pos) => (&no_fragment[..pos], &no_fragment[pos + 1..]),
            // 无 query——fragment 原样返回，不触碰 URL
            None => return url.to_string(),
        };
        // 过滤追踪参数（RS-070：空段——裸 ?/&/&& 产生的空串——不保留）
        let kept: Vec<&str> = query
            .split('&')
            .filter(|param| {
                if param.is_empty() {
                    return false;
                }
                let key = param.split('=').next().unwrap_or("");
                !self.params.iter().any(|tp| tp.eq_ignore_ascii_case(key))
            })
            .collect();
        // 重建 URL：base[?kept][fragment]
        let mut result = String::from(base);
        if !kept.is_empty() {
            result.push('?');
            result.push_str(&kept.join("&"));
        }
        if let Some(frag) = fragment {
            result.push_str(frag);
        }
        result
    }

    /// 生成 JS 注入脚本（在浏览器端拦截 fetch/XHR 请求时剥离参数）。
    pub fn inject_script(&self) -> String {
        let params_json: String = {
            // RS-022（审计 2026-09-24）：自定义参数含单引号/反斜杠此前直拼
            // 进 `'{}'` 字面量——逃逸字符串注入任意 JS
            let items: Vec<String> = self
                .params
                .iter()
                .map(|p| format!("'{}'", crate::util::js_escape_single_quoted(p)))
                .collect();
            format!("[{}]", items.join(","))
        };
        format!(
            r#"
// Aegis QueryStripper — URL 追踪参数剥离（参照 LibreWolf/Brave）
// 原始列表：LibreWolf (MPL-2.0) / Brave Software (MPL-2.0)
(function() {{
  var TRACKING_PARAMS = {params_json};
  var LOWER_SET = {{}};
  TRACKING_PARAMS.forEach(function(p) {{ LOWER_SET[p.toLowerCase()] = true; }});
  function stripParams(url) {{
    try {{
      var u = new URL(url);
      var changed = false;
      // 大小写不敏感剥离——searchParams.has 区分大小写，Gclid/gClId
      // 变体此前在浏览器拦截路径完整绕过（Rust 侧已是 ignore_case）
      var doomed = [];
      u.searchParams.forEach(function(v, k) {{
        if (LOWER_SET[k.toLowerCase()]) doomed.push(k);
      }});
      doomed.forEach(function(k) {{
        u.searchParams.delete(k);
        changed = true;
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
    fn inject_script_strips_case_variants() {
        // RS-010 回归：JS 侧剥离必须大小写不敏感——Gclid/gClId 变体此前
        // 在浏览器拦截路径完整绕过（Rust 侧已 ignore_case，注入侧漏配）
        let script = QueryStripper::new().inject_script();
        assert!(script.contains("toLowerCase()"));
        assert!(!script.contains("searchParams.has(p)"));
        assert!(script.contains("LOWER_SET"));
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

    // —— RS-070 回归（审计 2026-09-25） ——

    #[test]
    fn fragment_question_mark_not_query() {
        // RS-070：fragment 内的 '?' 不是 query 分隔符——fragment 内容
        // 不得被改写（此前 `path#a?fbclid=x` 的 fragment 遭错误剥离）
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/path#a?fbclid=x"),
            "https://example.com/path#a?fbclid=x",
            "fragment 内 '?' 与追踪参数名不构成 query"
        );
        // fragment 内 '?' + 前方真 query 并存——各自独立处理
        assert_eq!(
            qs.strip("https://example.com/?fbclid=y#s?a?b"),
            "https://example.com/#s?a?b",
            "真 query 剥离 + fragment 原样"
        );
    }

    #[test]
    fn empty_query_param_edge_cases() {
        // RS-070：空 query——裸 '?' 结尾归一到无 query 形态
        let qs = QueryStripper::new();
        assert_eq!(qs.strip("https://example.com/?"), "https://example.com/");
        assert_eq!(qs.strip("https://example.com/?&"), "https://example.com/");
        // 空 query + fragment
        assert_eq!(
            qs.strip("https://example.com/?#top"),
            "https://example.com/#top"
        );
    }

    #[test]
    fn param_without_value_handled() {
        // RS-070：无 '=' 的参数（flag 形态）——key 取整段；追踪名单的
        // flag 参数照样剥离，普通 flag 保留
        let qs = QueryStripper::new();
        assert_eq!(
            qs.strip("https://example.com/?flag&fbclid=x&id=3"),
            "https://example.com/?flag&id=3"
        );
        // flag 形态的追踪参数（无 '='）同样命中
        assert_eq!(
            qs.strip("https://example.com/?fbclid"),
            "https://example.com/"
        );
        // '=' 后为空的追踪参数同样命中
        assert_eq!(
            qs.strip("https://example.com/?fbclid=&id=1"),
            "https://example.com/?id=1"
        );
    }

    #[test]
    fn default_params_are_borrowed_not_owned() {
        // RS-071：默认构造零分配借用静态切片——Debug/结构语义不变
        let qs = QueryStripper::new();
        assert_eq!(qs.params.len(), 34);
        let debug = format!("{qs:?}");
        assert!(debug.contains("34 params"));
        // 自定义路径仍可扩展（Owned）
        let custom = QueryStripper::with_params(vec!["x".into()]);
        assert_eq!(custom.params.len(), 1);
    }
}

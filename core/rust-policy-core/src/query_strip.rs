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

    /// RS-164（审计 2026-09-25）：query 串过滤——追踪参数剔除与空段
    /// 弃置，从 strip 的内联逻辑提取为独立步骤。
    ///
    /// 此前「取 `=` 首段为 key」（`split('=').next()`）是内联的隐式约定，
    /// 无法独立观测；提取后本函数可单独单测，语义显式化：参数 key 是
    /// 首个 `=` 之前的部分（flag 形态整段即 key），空段一律丢弃。
    fn filter_query<'a>(&self, query: &'a str) -> Vec<&'a str> {
        query
            .split('&')
            .filter(|param| {
                if param.is_empty() {
                    return false;
                }
                let key = param.split('=').next().unwrap_or("");
                !self.params.iter().any(|tp| tp.eq_ignore_ascii_case(key))
            })
            .collect()
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
        // 过滤追踪参数（RS-164：提取的独立步骤）
        let kept = self.filter_query(query);
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
        // RS-242（2026-10-01 审计）：代理注册接口 Symbol 键单源引用
        //（描述串去品牌化——详见 ToStringGuard::REGISTER_SYMBOL）
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
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
    }} catch(e) {{
      // RS-248（2026-10-01 审计）：相对 URL 无 base 抛异常——此前原样
      // 放行（追踪参数在相对请求上畅通剥离绕过）。手工剥离与 Rust strip
      // 同语义：先分离 fragment 再定位 query，只动 query 段，保持相对形态
      //（绝对化会改变请求字符串）
      var hashIdx = url.indexOf('#');
      var rest = hashIdx >= 0 ? url.slice(0, hashIdx) : url;
      var hash = hashIdx >= 0 ? url.slice(hashIdx) : '';
      var qIdx = rest.indexOf('?');
      if (qIdx < 0) return url;
      var base = rest.slice(0, qIdx);
      var kept = rest.slice(qIdx + 1).split('&').filter(function(param) {{
        if (!param) return false;
        var key = param.split('=')[0];
        return !LOWER_SET[key.toLowerCase()];
      }});
      return kept.length ? (base + '?' + kept.join('&') + hash) : (base + hash);
    }}
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
  // RS-232（2026-09-26 审计）：显式参数转发——arguments[1] 写回赋值
  // 仅非严格模式合法（严格模式下不生效），改显式收集转发
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {{
    var rest = Array.prototype.slice.call(arguments, 2);
    return origOpen.apply(this, [method, stripParams(url)].concat(rest));
  }};

  // RS-242（2026-10-01 审计）：fetch/open 覆盖注册 ToStringGuard——
  // 未注册时 fetch.toString() 一行暴露包装源码（内含品牌特征）
  var __aegisReg = window[Symbol.for('{reg_sym}')];
  if (__aegisReg) {{
    __aegisReg(window.fetch, origFetch);
    __aegisReg(XMLHttpRequest.prototype.open, origOpen);
  }}
}})();
"#,
            params_json = params_json
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

    // —— RS-232 回归（审计 2026-09-26） ——

    #[test]
    fn xhr_open_forwards_arguments_explicitly() {
        // RS-232：XHR 拦截不得依赖 `arguments[1] = ...` 写回（仅非严格
        // 模式合法）——必须显式参数转发（method + 剥离后 url + rest）
        let script = QueryStripper::new().inject_script();
        assert!(
            script.contains("Array.prototype.slice.call(arguments, 2)"),
            "可选参（async/user/password）显式收集"
        );
        assert!(
            script.contains("origOpen.apply(this, [method, stripParams(url)].concat(rest))"),
            "显式转发剥离后的 url 与剩余参数"
        );
        assert!(
            !script.contains("arguments[1] ="),
            "arguments 写回形态必须移除（严格模式失效）"
        );
    }

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

    // —— RS-164（审计 2026-09-25）：filter_query 独立步骤单测 ——

    #[test]
    fn filter_query_key_is_segment_before_first_equals() {
        // key 语义显式锁定：首个 '=' 之前的部分；值内含 '=' 不影响判定
        let qs = QueryStripper::new();
        assert_eq!(
            qs.filter_query("fbclid=x=y"),
            Vec::<&str>::new(),
            "追踪参数连同值剔除"
        );
        assert_eq!(
            qs.filter_query("a=b=c"),
            vec!["a=b=c"],
            "普通参数 key=a 保留"
        );
    }

    #[test]
    fn filter_query_drops_empty_segments_and_flags() {
        // 空段（裸 &/&&）丢弃；flag 形态追踪参数（无 '='）命中剔除
        let qs = QueryStripper::new();
        assert_eq!(qs.filter_query(""), Vec::<&str>::new());
        assert_eq!(qs.filter_query("&&"), Vec::<&str>::new());
        assert_eq!(
            qs.filter_query("fbclid"),
            Vec::<&str>::new(),
            "flag 形态追踪参数剔除"
        );
        assert_eq!(qs.filter_query("keep&fbclid&&tail"), vec!["keep", "tail"]);
    }

    #[test]
    fn filter_query_case_insensitive_keys() {
        // 与 strip 口径一致：key 按ASCII 不区分大小写命中
        let qs = QueryStripper::new();
        assert_eq!(qs.filter_query("GCLID=x"), Vec::<&str>::new());
        assert_eq!(qs.filter_query("FbClId"), Vec::<&str>::new());
    }

    // —— RS-242/248 回归（审计 2026-10-01） ——

    #[test]
    fn js_strip_handles_relative_urls_manually() {
        // RS-248：JS 侧 stripParams 对相对 URL（new URL 无 base 抛异常）
        // 此前原样放行——现走手工剥离分支（与 Rust strip 同语义）
        let script = QueryStripper::new().inject_script();
        assert!(
            script.contains("var hashIdx = url.indexOf('#');"),
            "手工分支先分离 fragment（Rust strip 同语义）"
        );
        assert!(
            script.contains("var qIdx = rest.indexOf('?');"),
            "fragment 前缀中定位 query"
        );
        assert!(
            script.contains(
                "return kept.length ? (base + '?' + kept.join('&') + hash) : (base + hash);"
            ),
            "重建：全追踪参数剥 query 段，保留 fragment 与相对形态"
        );
        // 手工分支必须位于 catch 内（绝对 URL 仍走 URL 解析路径）
        let catch_pos = script.find("} catch(e) {").expect("catch 分支");
        let manual_pos = script.find("var hashIdx").expect("手工剥离");
        assert!(catch_pos < manual_pos, "手工剥离在异常兜底分支内");
    }

    #[test]
    fn fetch_and_xhr_wrappers_registered_with_tostring_guard() {
        // RS-242：fetch/open 覆盖必须注册 ToStringGuard——未注册时
        // fetch.toString() 一行暴露包装源码（内含品牌特征）
        let script = QueryStripper::new().inject_script();
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
        assert_eq!(
            script.matches(&format!("Symbol.for('{reg_sym}')")).count(),
            1,
            "注册接口引用单次（批量注册两包装）"
        );
        assert!(script.contains("__aegisReg(window.fetch, origFetch);"));
        assert!(script.contains("__aegisReg(XMLHttpRequest.prototype.open, origOpen);"));
    }
}

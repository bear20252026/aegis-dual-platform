//! Origin/URL canonicalization（蓝图阶段 F 第二推荐项）。
//!
//! 与 contracts/vectors/url-origin-valid|invalid.json 一致（http/https 放行——
//! data:/blob:/javascript:/userinfo/控制字符/无 host/超长拒绝——P0-01 同语义）。
//! 纯函数——无 I/O。

/// 已规范化的外部 URL；fragment 不参与副作用授权绑定。
///
/// RS-190（审计 2026-09-25）：字段级文档——本结构是授权绑定的载体，
/// 各字段语义由注释锁定，跨端（C#/Kotlin/Python）消费方据此对齐。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalExternalUrl {
    /// 小写 scheme——仅 "http" / "https"（其余在 canonicalize_external 拒绝）。
    pub scheme: String,
    /// 小写 host（已剥尾点、已拒非法字符）；默认端口（80/443）不出现在
    /// origin——host 字段不含端口，端口归一语义见 origin 字段。
    pub host: String,
    /// 授权绑定 origin（`scheme://host[:port]`）——默认端口省略，非默认
    /// 端口保留。授权相等性以此字段为准。
    pub origin: String,
    /// 规范化 path + query（fragment 已剥离——fragment 不参与副作用授权，
    /// `#` 之后内容不进入绑定比较）。
    pub canonical_parameters: String,
}

/// 解析并规范化外部 URL（仅 http/https——非法返回 None——fail-closed）。
pub fn canonicalize_external(raw: &str) -> Option<CanonicalExternalUrl> {
    const MAX_URL_LENGTH: usize = 8192;
    if raw.is_empty() || raw.len() > MAX_URL_LENGTH {
        return None;
    }
    if raw
        .bytes()
        .any(|b| b < 0x20 || b == 0x7f || b.is_ascii_whitespace())
    {
        return None;
    }
    let (raw_scheme, rest) = raw.split_once("://")?;
    let scheme = raw_scheme.to_ascii_lowercase();
    if scheme != "http" && scheme != "https" {
        return None; // 拒绝 data:/blob:/javascript:/file: 等（url-origin-invalid 向量）
    }
    let authority = rest.split(['/', '?', '#']).next()?;
    if authority.is_empty() || authority.contains('@') || authority.starts_with('[') {
        return None; // 无 host / userinfo（url-origin-invalid 向量）
    }
    let (raw_host, port) = if let Some((host, port)) = authority.rsplit_once(':') {
        if host.is_empty() {
            return None;
        }
        // RS-011（审计 2026-09-24）：host 段拒内嵌冒号——此前 rsplit_once
        // 取最后一段当端口，"host:8080:1234" 以 host="host:8080" 被接受
        //（合法端口掩盖非法 authority）
        if host.contains(':') {
            return None;
        }
        // 非法端口拒绝（contracts/vectors/url-origin-invalid——https://host:99999
        // ——u16 范围校验——WHATWG 同语义——P0-01）
        let Ok(port_num) = port.parse::<u16>() else {
            return None;
        };
        if port_num == 0 {
            return None;
        }
        (host, Some(port_num))
    } else {
        (authority, None)
    };
    let host = raw_host.to_ascii_lowercase();
    if host.is_empty() {
        return None;
    }
    // RS-012（审计 2026-09-24）：host 字符白名单 + 尾点剥离——与 C# 口径
    // 一致。尾点为合法 FQDN 根表示（example.org.）——剥离后归一；剥离后
    // 仅允许 [a-z0-9.-]（xn-- punycode 亦在集内），其余字符（下划线/空格/
    // 控制符等）一律拒绝
    let host = host.strip_suffix('.').unwrap_or(&host);
    if host.is_empty()
        || host.starts_with('.')
        || host.contains("..")
        || !host
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
    {
        return None;
    }
    // PY-071/072（审计 2026-09-25）：非点分十进制 IPv4 编码拒绝——整数
    //（2130706433）/0x 十六进制（0x7f000001）/简写（127.1）形态 OS 解析器
    // 均接受，同一 URL 双重解释是混淆面——对齐 C# UrlSafety/OriginPolicy
    // 口径（contracts/vectors/url-origin-invalid PY-071/072 向量）。
    // 全数字段且段数 ≠ 4 一律拒绝（4 段 = 合法点分 IPv4 字面量，保留）；
    // 0x 十六进制 host 单独拒绝
    let segments: Vec<&str> = host.split('.').collect();
    if segments.len() != 4
        && segments
            .iter()
            .all(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
    {
        return None;
    }
    if host.starts_with("0x")
        && host[2..]
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return None; // 0x 十六进制 host
    }
    let host = host.to_string();
    let canonical_authority = match port {
        Some(value)
            if !((scheme == "https" && value == 443) || (scheme == "http" && value == 80)) =>
        {
            format!("{host}:{value}")
        }
        _ => host,
    };
    let suffix = &rest[authority.len()..];
    // RS-059（审计 2026-09-25）：split 恒产生首元素——unwrap_or_default
    // 属冗余解包，改 split_once 显式表达「无 # 即整段」语义
    let without_fragment = suffix.split_once('#').map_or(suffix, |(before, _)| before);
    let canonical_parameters = match without_fragment {
        "" => "/".to_string(),
        query if query.starts_with('?') => format!("/{query}"),
        path => path.to_string(),
    };
    // RS-060（审计 2026-09-25）：origin 单次 format 构造后整体 move——
    // 此前 scheme.clone() + canonical_authority.clone() 双 clone
    let origin = format!("{scheme}://{canonical_authority}");
    Some(CanonicalExternalUrl {
        scheme,
        host: canonical_authority,
        origin,
        canonical_parameters,
    })
}

/// 解析外部 URL 的兼容入口（仅返回规范化 scheme 与 authority）。
pub fn try_parse_external(raw: &str) -> Option<(String, String)> {
    canonicalize_external(raw).map(|url| (url.scheme, url.host))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_origins_allow() {
        assert_eq!(
            try_parse_external("https://a.gov.cn/page"),
            Some(("https".into(), "a.gov.cn".into()))
        );
        assert_eq!(
            try_parse_external("http://example.org/"),
            Some(("http".into(), "example.org".into()))
        );
    }

    #[test]
    fn invalid_origins_deny() {
        // 与 contracts/vectors/url-origin-invalid.json 一致
        assert_eq!(try_parse_external("data:text/html,<script>"), None);
        assert_eq!(try_parse_external("blob:https://a.gov.cn/x"), None);
        assert_eq!(try_parse_external("javascript:alert(1)"), None);
        assert_eq!(try_parse_external("file:///C:/sensitive.txt"), None);
        assert_eq!(try_parse_external("https://user:pass@example.org/"), None);
        assert_eq!(try_parse_external("https:///nohost"), None);
        assert_eq!(try_parse_external("https://example.org:99999/"), None);
    }

    #[test]
    fn canonicalization_normalizes_origin_and_binds_path_query() {
        assert_eq!(
            canonicalize_external("HTTPS://Example.Org:443/a?b=1#ignored"),
            Some(CanonicalExternalUrl {
                scheme: "https".into(),
                host: "example.org".into(),
                origin: "https://example.org".into(),
                canonical_parameters: "/a?b=1".into(),
            })
        );
        assert_eq!(
            canonicalize_external("http://example.org:8080?x=1"),
            Some(CanonicalExternalUrl {
                scheme: "http".into(),
                host: "example.org:8080".into(),
                origin: "http://example.org:8080".into(),
                canonical_parameters: "/?x=1".into(),
            })
        );
    }

    // —— 边界补强：授权绑定安全相关的规范化语义（此前仅 3 例正向覆盖）——

    #[test]
    fn empty_and_oversized_urls_reject() {
        assert_eq!(canonicalize_external(""), None);
        // 超长（> 8192 字节）拒绝——防御授权绑定前的资源耗尽
        let oversized = format!("https://example.org/{}", "a".repeat(8200));
        assert_eq!(canonicalize_external(&oversized), None);
    }

    #[test]
    fn control_characters_and_whitespace_reject() {
        assert_eq!(try_parse_external("https://exa\u{0000}mple.org/"), None);
        assert_eq!(try_parse_external("https://example.org/a b"), None);
        assert_eq!(try_parse_external(" https://example.org/"), None);
        assert_eq!(try_parse_external("https://example.org/\u{7f}"), None);
    }

    #[test]
    fn fragment_only_differs_not_in_binding() {
        // fragment 不参与授权绑定：同一 path?query 不同 fragment 必须得到
        // 相同 canonical_parameters（否则同页锚点跳转被视为新授权面）
        let a = canonicalize_external("https://example.org/p?q=1#top").unwrap();
        let b = canonicalize_external("https://example.org/p?q=1#other").unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn default_port_elided_in_origin() {
        // 显式默认端口与省略端口得到相同 origin（授权绑定等价类）
        let explicit = canonicalize_external("https://example.org:443/x").unwrap();
        let elided = canonicalize_external("https://example.org/x").unwrap();
        assert_eq!(explicit.origin, elided.origin);
        let http_explicit = canonicalize_external("http://example.org:80/y").unwrap();
        let http_elided = canonicalize_external("http://example.org/y").unwrap();
        assert_eq!(http_explicit.origin, http_elided.origin);
    }

    #[test]
    fn port_zero_and_empty_host_reject() {
        assert_eq!(try_parse_external("https://example.org:0/"), None);
        assert_eq!(try_parse_external("https://:443/"), None);
        // authority 后紧跟 userinfo @ 一律拒绝（前向凭证混淆）
        assert_eq!(try_parse_external("https://@example.org/"), None);
    }

    #[test]
    fn bare_path_normalizes_to_slash() {
        // 空路径/纯 query/纯 fragment 全部归一到 "/" 起始形态
        let root = canonicalize_external("https://example.org").unwrap();
        assert_eq!(root.canonical_parameters, "/");
        let query_only = canonicalize_external("https://example.org?a=1").unwrap();
        assert_eq!(query_only.canonical_parameters, "/?a=1");
    }

    // —— RS-011/012 回归（审计 2026-09-24） ——

    #[test]
    fn host_with_embedded_colon_rejected() {
        // RS-011：host 段内嵌冒号此前借合法端口段被接受
        assert_eq!(try_parse_external("https://evil:8080:1234/"), None);
        assert_eq!(try_parse_external("https://a:b:99/"), None);
    }

    #[test]
    fn host_character_whitelist_and_trailing_dot() {
        // RS-012：字符白名单 + 尾点剥离
        assert!(
            try_parse_external("https://example.org./x").is_some(),
            "尾点 FQDN 剥离后放行"
        );
        let stripped = canonicalize_external("https://example.org./x").unwrap();
        assert_eq!(stripped.host, "example.org", "尾点剥离后 origin 归一");
        assert_eq!(
            try_parse_external("https://exa mple.org/"),
            None,
            "空格拒绝"
        );
        assert_eq!(
            try_parse_external("https://exa_mple.org/"),
            None,
            "下划线拒绝"
        );
        assert_eq!(
            try_parse_external("https://exa\"mple.org/"),
            None,
            "引号拒绝"
        );
        assert!(
            try_parse_external("https://xn--e1afmkfd.xn--p1ai/").is_some(),
            "punycode 字母数字在白名单内"
        );
        assert_eq!(
            try_parse_external("https://.example.org/"),
            None,
            "裸点拒绝"
        );
    }

    // —— RS-057/058 回归（审计 2026-09-25） ——

    #[test]
    fn alternate_ipv4_encodings_rejected() {
        // RS-057/PY-071：非点分十进制 IPv4 编码拒绝（OS 解析器双重解释混淆面）
        assert_eq!(
            try_parse_external("https://2130706433/"),
            None,
            "整数形 IPv4 拒绝"
        );
        assert_eq!(
            try_parse_external("https://0x7f000001/"),
            None,
            "0x 十六进制形拒绝"
        );
        assert_eq!(
            try_parse_external("https://127.1/"),
            None,
            "简写形（2 段全数字）拒绝"
        );
        // 4 段点分十进制字面量保留（合法 IPv4）
        assert!(
            try_parse_external("https://127.0.0.1/").is_some(),
            "4 段点分 IPv4 保留"
        );
    }

    #[test]
    fn max_url_length_exact_boundary() {
        // RS-057：8192 恰好边界——== 上限放行，+1 拒绝
        let prefix = "https://example.org/";
        let exact = format!("{prefix}{}", "a".repeat(8192 - prefix.len()));
        assert_eq!(exact.len(), 8192);
        assert!(canonicalize_external(&exact).is_some(), "恰 8192 字节放行");
        let over = format!("{exact}a");
        assert_eq!(over.len(), 8193);
        assert_eq!(canonicalize_external(&over), None, "8193 字节拒绝");
    }

    #[test]
    fn port_u16_boundary_values() {
        // RS-058：u16 端口边界——1/65535 合法，65536 溢出拒绝
        assert!(
            try_parse_external("https://example.org:1/").is_some(),
            "端口 1 合法"
        );
        assert!(
            try_parse_external("https://example.org:65535/").is_some(),
            "端口 65535 合法"
        );
        assert_eq!(
            try_parse_external("https://example.org:65536/"),
            None,
            "端口 65536 溢出 u16 拒绝"
        );
    }

    #[test]
    fn bracketed_ipv6_authority_rejected() {
        // RS-177：'[' 开头 authority 此前拒码路径零用例——IPv6 字面量
        // authority 在 host 白名单化管线（[a-z0-9.-]）必然无法表达，
        // fail-closed 拒绝并锁定（含带端口/裸字面量/方括号内嵌冒号形态）
        assert_eq!(try_parse_external("https://[2001:db8::1]/"), None);
        assert_eq!(try_parse_external("https://[::1]:8080/x"), None);
        assert_eq!(try_parse_external("http://[::1]/"), None);
        // 未闭合方括号同样拒绝（同分支前置 starts_with('[')）
        assert_eq!(try_parse_external("https://[2001:db8::1/x"), None);
        // 正常 host 不受影响（回归锚点）
        assert!(try_parse_external("https://example.org/").is_some());
    }
}

//! Origin/URL canonicalization（蓝图阶段 F 第二推荐项）。
//!
//! 与 contracts/vectors/url-origin-valid|invalid.json 一致（http/https 放行——
//! data:/blob:/javascript:/userinfo/控制字符/无 host/超长拒绝——P0-01 同语义）。
//! 纯函数——无 I/O。

/// 已规范化的外部 URL；fragment 不参与副作用授权绑定。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalExternalUrl {
    pub scheme: String,
    pub host: String,
    pub origin: String,
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
    let canonical_authority = match port {
        Some(value)
            if !((scheme == "https" && value == 443) || (scheme == "http" && value == 80)) =>
        {
            format!("{host}:{value}")
        }
        _ => host.clone(),
    };
    let suffix = &rest[authority.len()..];
    let without_fragment = suffix.split('#').next().unwrap_or_default();
    let canonical_parameters = match without_fragment {
        "" => "/".to_string(),
        query if query.starts_with('?') => format!("/{query}"),
        path => path.to_string(),
    };
    Some(CanonicalExternalUrl {
        scheme: scheme.clone(),
        host: canonical_authority.clone(),
        origin: format!("{scheme}://{canonical_authority}"),
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
}

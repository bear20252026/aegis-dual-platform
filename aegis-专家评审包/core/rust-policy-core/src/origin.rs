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
}

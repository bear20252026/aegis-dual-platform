//! Origin/URL canonicalization（蓝图阶段 F 第二推荐项）。
//!
//! 与 contracts/vectors/url-origin-valid|invalid.json 一致（http/https 放行——
//! data:/blob:/javascript:/userinfo/控制字符/无 host/超长拒绝——P0-01 同语义）。
//! 纯函数——无 I/O。

/// 解析外部 URL（仅 http/https——非法返回 None——fail-closed）。
pub fn try_parse_external(raw: &str) -> Option<(String, String)> {
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
    let (scheme, rest) = raw.split_once("://")?;
    if scheme != "http" && scheme != "https" {
        return None; // 拒绝 data:/blob:/javascript:/file: 等（url-origin-invalid 向量）
    }
    let host = rest.split(['/', '?', '#']).next()?;
    if host.is_empty() || host.contains('@') {
        return None; // 无 host / userinfo（url-origin-invalid 向量）
    }
    if let Some((h, port)) = host.rsplit_once(':') {
        if h.is_empty() {
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
    }
    Some((scheme.to_string(), host.to_string()))
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
}

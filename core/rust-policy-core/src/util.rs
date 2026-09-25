// 由账号2生成
//! 工具函数模块（消除跨模块重复实现）。
//!
//! 提供：
//! - `hex_digit`：十六进制字符转数值（原 session_state/security_policy 重复）
//! - `extract_hostname`：从 URL 提取主机名（原 origin/adblock/space_routing 重复）
//! - `extract_host`：从 URL 提取小写主机名（原 adblock 专用）
//!
//! 设计：纯函数，零状态，零依赖，可被任何模块安全引用。

/// 十六进制 ASCII 字节转数值（0-15）。
///
/// `b'0'`..`b'9'` → 0..9，`b'a'`..`b'f'` / `b'A'`..`b'F'` → 10..15。
/// 非十六进制字节返回 `None`。
#[inline]
pub fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

/// 从 URL 提取主机名（保留原始大小写，含端口号）。
///
/// 处理 `scheme://host:port/path` 格式；无 scheme 时视为裸主机名。
/// 返回值不含路径、查询和 fragment。
///
/// RS-013（审计 2026-09-24）：authority 终止符从 `/` 扩到 `/?#`——
/// 此前 `https://example.com?u=a@b` 的 query 内 `@` 被当 userinfo，
/// 主机名错提为 `b`。
///
/// # 示例
/// ```
/// use aegis_policy_core::util::extract_hostname;
/// assert_eq!(extract_hostname("https://example.com/path"), "example.com");
/// assert_eq!(extract_hostname("http://localhost:3000/"), "localhost:3000");
/// ```
pub fn extract_hostname(url: &str) -> &str {
    let without_scheme = if let Some(pos) = url.find("://") {
        &url[pos + 3..]
    } else {
        url
    };
    // authority = 首个 / ? # 之前的部分（WHATWG 语义）
    let authority_end = without_scheme
        .find(['/', '?', '#'])
        .unwrap_or(without_scheme.len());
    let authority = &without_scheme[..authority_end];
    // 剥 userinfo（user@host——authority 内任意 @ 之后是 host）
    match authority.find('@') {
        Some(at) => &authority[at + 1..],
        None => authority,
    }
}

/// 从 URL 提取小写主机名（不含端口号）。
///
/// 用于广告拦截等需要大小写不敏感匹配的场景。
pub fn extract_host(url: &str) -> Option<String> {
    let hostname = extract_hostname(url);
    // 去掉端口号——IPv6 字面量 [::1]:8080 先剥方括号段再判定（此前 rfind(':')
    // 把 "[::1" 截断成非法形态）
    let host = if hostname.starts_with('[') {
        match hostname.find(']') {
            Some(end) => &hostname[1..end],
            None => hostname,
        }
    } else if let Some(pos) = hostname.find(':') {
        // RS-014（审计 2026-09-24）：裸 IPv6（≥2 个冒号）无法区分 host:port
        // 语义——fail-closed 返回 None，绝不按首个 ':' 截断出伪主机名
        // （此前 "2001:db8::1" 被截成 "2001"）
        if hostname[pos + 1..].contains(':') {
            return None;
        }
        &hostname[..pos]
    } else {
        hostname
    };
    if host.is_empty() {
        None
    } else {
        Some(host.to_lowercase())
    }
}

/// 转义 JS 单引号字符串字面量（RS-022/023/024 共用单源）。
///
/// 自定义参数/字体名/vendor 字符串此前直拼 `'{}'`——含 `'` 或 `\` 即
/// 逃逸字符串字面量注入任意 JS。反斜杠先转义、单引号次之（顺序不可换），
/// 行分隔符一并拒绝（JS 字符串字面量不允许裸换行）。
pub fn js_escape_single_quoted(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_digit_valid() {
        assert_eq!(hex_digit(b'0'), Some(0));
        assert_eq!(hex_digit(b'9'), Some(9));
        assert_eq!(hex_digit(b'a'), Some(10));
        assert_eq!(hex_digit(b'f'), Some(15));
        assert_eq!(hex_digit(b'A'), Some(10));
        assert_eq!(hex_digit(b'F'), Some(15));
    }

    #[test]
    fn hex_digit_invalid() {
        assert_eq!(hex_digit(b'g'), None);
        assert_eq!(hex_digit(b'x'), None);
        assert_eq!(hex_digit(b' '), None);
    }

    #[test]
    fn extract_hostname_basic() {
        assert_eq!(extract_hostname("https://example.com/path"), "example.com");
        assert_eq!(extract_hostname("http://example.com"), "example.com");
        assert_eq!(extract_hostname("example.com/path"), "example.com");
    }

    #[test]
    fn extract_hostname_with_port() {
        assert_eq!(
            extract_hostname("http://localhost:3000/path"),
            "localhost:3000"
        );
    }

    #[test]
    fn extract_host_lowercase_no_port() {
        assert_eq!(
            extract_host("https://Example.COM/path"),
            Some("example.com".to_string())
        );
        assert_eq!(
            extract_host("http://localhost:3000/"),
            Some("localhost".to_string())
        );
    }

    #[test]
    fn extract_host_empty() {
        assert_eq!(extract_host(""), None);
    }

    // —— RS-013/014 回归（审计 2026-09-24） ——

    #[test]
    fn extract_hostname_query_at_not_userinfo() {
        // RS-013：query 中的 @ 不再被当 userinfo——authority 终止符含 ?
        assert_eq!(
            extract_hostname("https://example.com?u=a@evil"),
            "example.com"
        );
        assert_eq!(
            extract_hostname("https://example.com/p?x=@y"),
            "example.com"
        );
        // 真 userinfo（@ 在 authority 内）仍剥除
        assert_eq!(
            extract_hostname("https://user@example.com/path"),
            "example.com"
        );
    }

    #[test]
    fn extract_host_bare_ipv6_rejected() {
        // RS-014：裸 IPv6 ≥2 个冒号 fail-closed 返回 None——此前按首个
        // ':' 截断出 "2001" 伪主机名污染匹配基座
        assert_eq!(extract_host("2001:db8::1"), None);
        assert_eq!(extract_host("http://2001:db8::1/x"), None);
        // host:port（单冒号）语义不受影响
        assert_eq!(extract_host("localhost:3000"), Some("localhost".into()));
        // 方括号 IPv6 仍正常剥段
        assert_eq!(extract_host("[::1]:8080"), Some("::1".into()));
    }

    #[test]
    fn js_escape_single_quoted_neutralizes_injection() {
        assert_eq!(
            js_escape_single_quoted("a'b"),
            "a\\'b",
            "单引号必须转义（逃逸字符串字面量）"
        );
        assert_eq!(
            js_escape_single_quoted("a\\b"),
            "a\\\\b",
            "反斜杠先转义（防把转义引号的反斜杠吃掉）"
        );
        assert_eq!(js_escape_single_quoted("a\nb"), "a\\nb");
    }
}

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
/// 返回值不含路径和查询参数。
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
    let host_end = without_scheme.find('/').unwrap_or(without_scheme.len());
    &without_scheme[..host_end]
}

/// 从 URL 提取小写主机名（不含端口号）。
///
/// 用于广告拦截等需要大小写不敏感匹配的场景。
pub fn extract_host(url: &str) -> Option<String> {
    let hostname = extract_hostname(url);
    // 去掉端口号
    let host = if let Some(pos) = hostname.rfind(':') {
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
}

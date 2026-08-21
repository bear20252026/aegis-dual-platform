/*
 * security_policy.rs — 集中安全策略（照搬 Omni Browser SecurityPolicy.kt 本地化适配）。
 *
 * 原始版权：Omni Browser - Copyright (C) 2026 RebelRoot Ltd
 * 原始许可：GNU General Public License v3.0
 * 来源：https://github.com/REBEL-ROOT/omni-browser
 * 改动：将 Kotlin 实现翻译为 Rust，适配 Aegis 架构。
 */

/// 安全导航 scheme 白名单。
const ALLOWED_NAVIGATION_SCHEMES: &[&str] = &["http", "https", "about", "file", "content"];

/// 外部意图危险 scheme 黑名单。
const DANGEROUS_EXTERNAL_SCHEMES: &[&str] =
    &["javascript", "data", "blob", "intent", "market", "chrome"];

/// Windows 保留设备名。
const RESERVED_NAMES: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

const MAX_FILENAME_LENGTH: usize = 200;

/// 集中安全策略（照搬 Omni Browser SecurityPolicy）。
pub struct SecurityPolicy;

impl SecurityPolicy {
    /// 检查 scheme 是否为安全导航 scheme（null/空视为相对 URL——允许）。
    pub fn is_valid_navigation_scheme(scheme: Option<&str>) -> bool {
        match scheme {
            None | Some("") => true,
            Some(s) => ALLOWED_NAVIGATION_SCHEMES
                .iter()
                .any(|allowed| allowed.eq_ignore_ascii_case(s)),
        }
    }

    /// 检查 scheme 是否为外部意图危险 scheme（空返回 false）。
    pub fn is_dangerous_external_scheme(scheme: Option<&str>) -> bool {
        match scheme {
            None | Some("") => false,
            Some(s) => DANGEROUS_EXTERNAL_SCHEMES
                .iter()
                .any(|dangerous| dangerous.eq_ignore_ascii_case(s)),
        }
    }

    /// 文件名安全化（防路径遍历/空字节/控制字符/保留名攻击）。
    ///
    /// 处理：
    /// - URL 编码的遍历序列（%2e%2e%2f）
    /// - 空字节注入（%00, \u0000）
    /// - 控制字符（ASCII < 32）
    /// - 路径分隔符（../, ..\）
    /// - Windows 保留设备名
    /// - 过长文件名（保留扩展名）
    pub fn sanitize_filename(name: Option<&str>) -> String {
        let name = match name {
            None | Some("") => return "download".to_string(),
            Some(n) => n.trim(),
        };

        // URL 解码（捕获编码遍历序列——零依赖手动实现）
        let mut sanitized = Self::url_decode(name).unwrap_or_else(|| name.to_string());

        // 去空字节
        sanitized = sanitized.replace('\u{0000}', "");

        // 去控制字符（保留换行/回车/制表）
        sanitized.retain(|c| c as u32 >= 32 || c == '\n' || c == '\r' || c == '\t');

        // 去路径分隔符和遍历序列
        for sep in &["../", "..\\", "/", "\\", ":", "|", "?", "*", "\""] {
            sanitized = sanitized.replace(sep, "");
        }

        // 折叠剩余双点
        sanitized = sanitized.replace("..", ".");

        // 去首尾点/空格（Windows 兼容）
        sanitized = sanitized.trim_start_matches(['.', ' ']).to_string();
        sanitized = sanitized.trim_end_matches(['.', ' ']).to_string();

        if sanitized.is_empty() {
            return "download".to_string();
        }

        // 检查 Windows 保留设备名
        let base_name = sanitized
            .rsplit_once('.')
            .map(|(b, _)| b)
            .unwrap_or(&sanitized)
            .to_uppercase();
        if RESERVED_NAMES.contains(&base_name.as_str()) {
            sanitized = format!("_{}", sanitized);
        }

        // 长度限制（保留扩展名）
        if sanitized.len() > MAX_FILENAME_LENGTH {
            if let Some(dot_pos) = sanitized.rfind('.') {
                let ext = &sanitized[dot_pos..];
                let max_base = MAX_FILENAME_LENGTH.saturating_sub(ext.len());
                let base_end = max_base.min(dot_pos);
                sanitized = format!("{}{}", &sanitized[..base_end], ext);
            } else {
                sanitized.truncate(MAX_FILENAME_LENGTH);
            }
        }

        if sanitized.is_empty() {
            "download".to_string()
        } else {
            sanitized
        }
    }

    /// 手动 URL 解码（零依赖——处理 %XX 编码）。
    pub fn url_decode(input: &str) -> Option<String> {
        let bytes = input.as_bytes();
        let mut result = Vec::with_capacity(bytes.len());
        let mut i = 0;
        while i < bytes.len() {
            if bytes[i] == b'%' && i + 2 < bytes.len() {
                let hi = hex_digit(bytes[i + 1])?;
                let lo = hex_digit(bytes[i + 2])?;
                result.push((hi << 4) | lo);
                i += 3;
            } else {
                result.push(bytes[i]);
                i += 1;
            }
        }
        String::from_utf8(result).ok()
    }
}

/// 十六进制字符转数字（辅助函数）。
fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn https_scheme_valid() {
        assert!(SecurityPolicy::is_valid_navigation_scheme(Some("https")));
    }

    #[test]
    fn javascript_dangerous() {
        assert!(SecurityPolicy::is_dangerous_external_scheme(Some(
            "javascript"
        )));
    }

    #[test]
    fn sanitize_path_traversal() {
        assert!(!SecurityPolicy::sanitize_filename(Some("../etc/passwd")).contains(".."));
    }

    #[test]
    fn sanitize_null_byte() {
        let result = SecurityPolicy::sanitize_filename(Some("file\u{0000}.txt"));
        assert!(!result.contains('\u{0000}'));
    }

    #[test]
    fn sanitize_empty_returns_download() {
        assert_eq!(SecurityPolicy::sanitize_filename(None), "download");
        assert_eq!(SecurityPolicy::sanitize_filename(Some("")), "download");
    }
}

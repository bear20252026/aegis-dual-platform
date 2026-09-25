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
    /// - Windows 保留设备名（RS-114：截断后复查）
    /// - RTL 双向控制符（RS-113：扩展名伪装面）
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

        // RS-113（审计 2026-09-25）：剥 RTL 双向控制符——U+202E（RLO）等
        // 可把 "exe.jpg" 视觉伪装成 "gjp.exe"（扩展名伪装/钓鱼面）
        sanitized = sanitized
            .chars()
            .filter(|c| {
                !matches!(
                    c,
                    '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}' | '\u{200E}' | '\u{200F}'
                )
            })
            .collect();

        // 去路径分隔符和遍历序列
        for sep in &["../", "..\\", "/", "\\", ":", "|", "?", "*", "\""] {
            sanitized = sanitized.replace(sep, "");
        }

        // 折叠剩余双点——RS-017（审计 2026-09-24）：单趟 replace 不闭合
        //（"...." 单趟后仍剩 ".."，嵌套遍历序列逃逸），fixpoint 循环到
        // 不再含 ".."。每趟 replace 严格缩短串长——必然终止
        while sanitized.contains("..") {
            sanitized = sanitized.replace("..", ".");
        }

        // 去首尾点/空格（Windows 兼容）
        sanitized = sanitized.trim_start_matches(['.', ' ']).to_string();
        sanitized = sanitized.trim_end_matches(['.', ' ']).to_string();

        if sanitized.is_empty() {
            return "download".to_string();
        }

        // 检查 Windows 保留设备名（RS-114：helper 抽出供截断后复查）
        Self::ensure_not_reserved(&mut sanitized);

        // 长度限制（保留扩展名）——全部经 floor_char_boundary 类似语义：
        // 字节索引切片落在多字节 UTF-8 字符中间即 panic（文件名攻击者可控）
        if sanitized.len() > MAX_FILENAME_LENGTH {
            if let Some(dot_pos) = sanitized.rfind('.') {
                let ext = &sanitized[dot_pos..];
                let max_base = MAX_FILENAME_LENGTH.saturating_sub(ext.len());
                let base_end = max_base.min(dot_pos);
                let base_end = floor_boundary(&sanitized, base_end);
                sanitized = format!("{}{}", &sanitized[..base_end], ext);
            } else {
                let cut = floor_boundary(&sanitized, MAX_FILENAME_LENGTH);
                sanitized.truncate(cut);
            }

            // RS-114（审计 2026-09-25）：截断后复查保留名——此前检查仅在
            // 截断前执行，"CONX.ffff..." 截断后 base 变 "CON" 即绕过保留名
            // 消解（截断保头部，可把非保留 base 裁成保留名）
            if sanitized.is_empty() {
                return "download".to_string();
            }
            Self::ensure_not_reserved(&mut sanitized);
        }

        if sanitized.is_empty() {
            "download".to_string()
        } else {
            sanitized
        }
    }
}

/// 向下取整到 UTF-8 字符边界（cut 处落在多字节字符中间时回退到字符起点）。
/// 文件名截断用——字节切片落在多字节 UTF-8 字符中间会 panic。
fn floor_boundary(s: &str, cut: usize) -> usize {
    if cut >= s.len() {
        return s.len();
    }
    let mut i = cut;
    while i > 0 && !s.is_char_boundary(i) {
        i -= 1;
    }
    i
}

impl SecurityPolicy {
    /// Windows 保留设备名检查 + `_` 前缀消解（RS-114：抽 helper 供截断后复查）。
    fn ensure_not_reserved(sanitized: &mut String) {
        let base_name = sanitized
            .rsplit_once('.')
            .map(|(b, _)| b)
            .unwrap_or(sanitized.as_str())
            .to_uppercase();
        if RESERVED_NAMES.contains(&base_name.as_str()) {
            *sanitized = format!("_{sanitized}");
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

use crate::util::hex_digit;

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

    #[test]
    fn sanitize_dot_folding_is_fixpoint() {
        // RS-017 回归：单趟 ".."→"." 折叠不闭合（"...." 单趟后仍剩 ".."）——
        // fixpoint 后任何输入不得残留路径遍历序列
        for input in ["....", "..%2F..", "a....b", "../../../../etc/passwd"] {
            let out = SecurityPolicy::sanitize_filename(Some(input));
            assert!(!out.contains(".."), "输入 {input} 折叠后残留 ..：{out}");
        }
    }

    // —— RS-112 回归（审计 2026-09-25） ——

    #[test]
    fn reserved_names_covered_case_insensitive() {
        // RS-112：Windows 保留设备名（含大小写变体）必须加 _ 前缀
        assert!(SecurityPolicy::sanitize_filename(Some("CON.txt")).starts_with('_'));
        assert!(SecurityPolicy::sanitize_filename(Some("con.txt")).starts_with('_'));
        assert!(SecurityPolicy::sanitize_filename(Some("Com1.dat")).starts_with('_'));
        assert!(SecurityPolicy::sanitize_filename(Some("lpt9")).starts_with('_'));
        // 非保留名不加前缀
        assert_eq!(
            SecurityPolicy::sanitize_filename(Some("config.txt")),
            "config.txt"
        );
    }

    #[test]
    fn long_filename_truncated_keeping_extension_no_panic() {
        // RS-112：超长截断保留扩展名 + 多字节字符截断不 panic
        let long_ascii = format!("{}.txt", "a".repeat(300));
        let out = SecurityPolicy::sanitize_filename(Some(&long_ascii));
        assert!(out.len() <= MAX_FILENAME_LENGTH, "截断生效：{}", out.len());
        assert!(out.ends_with(".txt"), "扩展名保留");
        // 多字节（CJK 每字 3 字节）截断落在字符边界内
        let cjk = format!("{}{}.txt", "汉".repeat(120), "a".repeat(50));
        let out = SecurityPolicy::sanitize_filename(Some(&cjk));
        assert!(out.len() <= MAX_FILENAME_LENGTH);
        assert!(out.ends_with(".txt"));
        // 纯多字节（无扩展名）截断不 panic
        let _ = SecurityPolicy::sanitize_filename(Some(&"汉".repeat(150)));
    }

    #[test]
    fn url_decode_traversal_sequences() {
        // RS-112：%XX 解码路径——编码遍历序列/普通字符往返
        assert_eq!(
            SecurityPolicy::url_decode("%2e%2e%2f").as_deref(),
            Some("../")
        );
        assert_eq!(SecurityPolicy::url_decode("a%20b").as_deref(), Some("a b"));
        // 非 UTF-8 字节序列 → None（fail-closed）
        assert_eq!(SecurityPolicy::url_decode("%ff%fe"), None);
        // 截断的 % 编码（尾部无两个 hex 位）按字面保留
        assert_eq!(SecurityPolicy::url_decode("100%").as_deref(), Some("100%"));
    }

    // —— RS-113 回归（审计 2026-09-25） ——

    #[test]
    fn rtl_bidi_controls_stripped() {
        // RS-113：RTL 双向控制符剥离——U+202E（RLO）可把 "exe.jpg" 视觉
        // 伪装成 "gjp.exe"；剥离后伪装面消失
        let poisoned = "file\u{202E}exe.jpg";
        let out = SecurityPolicy::sanitize_filename(Some(poisoned));
        assert!(!out.contains('\u{202E}'), "RLO 必须被剥离：{out}");
        assert_eq!(out, "fileexe.jpg");
        // 全系双向控制符（LRE/LRO/PDF/ISOLI~3/LRM/RLM）
        for ctrl in [
            '\u{202A}', '\u{202B}', '\u{202C}', '\u{202D}', '\u{202E}', '\u{2066}', '\u{2067}',
            '\u{2068}', '\u{2069}', '\u{200E}', '\u{200F}',
        ] {
            let name = format!("a{ctrl}b.txt");
            let out = SecurityPolicy::sanitize_filename(Some(&name));
            assert!(!out.contains(ctrl), "控制符 {:#x} 必须被剥离", ctrl as u32);
        }
    }

    // —— RS-114 回归（审计 2026-09-25） ——

    #[test]
    fn reserved_name_rechecked_after_truncation() {
        // RS-114：截断保头部可把非保留 base 裁成保留名——"CONX.ffff.."
        //（总长 201）截断后 base = "CON"，此前截断前检查不复查即绕过
        let input = format!("CONX.{}", "f".repeat(196));
        assert_eq!(input.len(), 201, "必须触发截断");
        let out = SecurityPolicy::sanitize_filename(Some(&input));
        assert!(
            !out.to_uppercase().starts_with("CON"),
            "截断后的保留名 base 必须被复查消解：{out}"
        );
        assert!(out.starts_with("_CON"), "复查后加 _ 前缀：{out}");
        // 对照：未触发截断的正常保留名路径不受影响
        assert!(SecurityPolicy::sanitize_filename(Some("PRN.doc")).starts_with('_'));
    }

    // —— RS-115 回归（审计 2026-09-25） ——

    #[test]
    fn scheme_checks_are_case_insensitive() {
        // RS-115：scheme 大小写变体——白名单/黑名单均 ASCII 大小写折叠
        assert!(SecurityPolicy::is_valid_navigation_scheme(Some("HTTPS")));
        assert!(SecurityPolicy::is_valid_navigation_scheme(Some("Http")));
        assert!(SecurityPolicy::is_valid_navigation_scheme(Some("ABOUT")));
        assert!(!SecurityPolicy::is_valid_navigation_scheme(Some("FTP")));
        assert!(SecurityPolicy::is_dangerous_external_scheme(Some(
            "JAVASCRIPT"
        )));
        assert!(SecurityPolicy::is_dangerous_external_scheme(Some("Data")));
        assert!(!SecurityPolicy::is_dangerous_external_scheme(Some("HTTPS")));
    }
}

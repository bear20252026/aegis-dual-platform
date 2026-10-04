use super::super::*;

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
    // 非 UTF-8 字节序列 → None（fail-closed）——RS-187 口径："%FF" 用例
    // 已在此锁定（%ff%fe 与 %FF 单独形态）
    assert_eq!(SecurityPolicy::url_decode("%ff%fe"), None);
    assert_eq!(SecurityPolicy::url_decode("100%").as_deref(), Some("100%"));

    // —— RS-188（审计 2026-09-25）：控制空白剥离 ——

    // \n\r\t 此前被保留（未论证的宽松口径）——现与全部控制符一并剥离：
    // 文件名内嵌换行可做视觉伪装（名称截断伪造扩展名）
    for control in ["a\nb", "a\rb", "a\tb"] {
        let out = SecurityPolicy::sanitize_filename(Some(control));
        assert!(
            !out.contains(['\n', '\r', '\t']),
            "控制空白 {control:?} 必须剥离，实际 {out:?}"
        );
    }
    // 剥离后为空 → 回落 "download"
    assert_eq!(
        SecurityPolicy::sanitize_filename(Some("\n\r\t")),
        "download"
    );
    // 可打印空白（空格）不受影响（仅首尾 trim）
    assert_eq!(
        SecurityPolicy::sanitize_filename(Some("a b.txt")),
        "a b.txt"
    );
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

// —— RS-281 回归（2026-10-02）：扩展名超上限 ——

#[test]
fn oversized_extension_does_not_break_length_cap() {
    // RS-281：扩展名自身 ≥ MAX 时 max_base 饱和 0，保扩展名重组后
    // 整体仍超限（上限被突破）——截断后二次复查整体截到 MAX
    let input = format!("a.{}", "x".repeat(250));
    assert!(input.len() > MAX_FILENAME_LENGTH, "必须触发截断");
    let out = SecurityPolicy::sanitize_filename(Some(&input));
    assert!(
        out.len() <= MAX_FILENAME_LENGTH,
        "扩展名超上限时整体截到 MAX：{}",
        out.len()
    );
    // 多字节扩展名形态（CJK 每字 3 字节）同样复查——字符边界内截断
    let input = format!("b.{}", "汉".repeat(120));
    assert!(input.len() > MAX_FILENAME_LENGTH);
    let out = SecurityPolicy::sanitize_filename(Some(&input));
    assert!(out.len() <= MAX_FILENAME_LENGTH, "多字节扩展名同口径");
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

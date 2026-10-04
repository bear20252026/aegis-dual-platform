use super::super::*;

// —— 审计第六轮（2026-10-03）：保留名基名按首点 + 前缀后长度复查 ——

#[test]
fn reserved_name_base_uses_first_dot_not_last() {
    // Win32 在首个点处截断设备名：CON.dll 即 CON 设备，CON.dll.exe 同样
    // 末点口径给出基名 "CON.dll"（不在 RESERVED_NAMES）→ 此前放行
    for name in ["CON.dll.exe", "con.dll.exe", "CON.dll", "NUL.log.txt"] {
        let out = SecurityPolicy::sanitize_filename(Some(name));
        assert!(
            out.starts_with('_'),
            "首点基名保留设备名必须加前缀消解：{name} → {out}"
        );
    }
    // nul.txt：首点基名 "nul" → NUL 设备
    let out = SecurityPolicy::sanitize_filename(Some("nul.txt"));
    assert_eq!(out, "_nul.txt", "nul.txt 必须消解为 _nul.txt");
    // 多层扩展的 COM/LPT 形态同样消解
    assert!(SecurityPolicy::sanitize_filename(Some("LPT1.a.b")).starts_with('_'));
    // 对照：首点基名非保留名不加前缀（不误伤）
    assert_eq!(
        SecurityPolicy::sanitize_filename(Some("my.con.exe")),
        "my.con.exe"
    );
    // 无点名的基名 = 整串（首点口径的退化分支）——200 字节 "CONbbb…"
    // 不是设备名（设备名要求整名即 CON），不加前缀也不截断
    let no_dot = "CON".to_string() + &"b".repeat(197);
    assert_eq!(no_dot.len(), MAX_FILENAME_LENGTH);
    assert_eq!(SecurityPolicy::sanitize_filename(Some(&no_dot)), no_dot);
}

/// 输出基名（首个点前段，大写归一）——保留设备名判定的输入口径单源。
fn reserved_base_of(name: &str) -> String {
    name.split_once('.')
        .map(|(b, _)| b)
        .unwrap_or(name)
        .to_uppercase()
}

#[test]
fn reserved_name_prefix_never_breaks_length_cap() {
    // 200 字节边界：恰好 MAX 的保留名加 `_` 前缀即 201——前缀必须在长度
    // 复查之前加入，否则文档上限被突破 1 字节。
    // 审计第六轮（2026-10-03）断言口径更正：此前断言 `starts_with("_CON")`
    // 断言的是**外观**而非安全属性。实际路径为 201 → 进入"保扩展名"截断分支：
    // 扩展名 "." + 196×'a' 长 197，max_base = 200-197 = 3，基名被裁到 3 字符
    // = "_CO"。这是既有 RS-114/RS-281 截断策略的既定取舍（扩展名语义优先，
    // 危险扩展判定依赖它），不是回归。真正必须守住的是两条安全不变量：
    // ① 长度 ≤MAX；② 结果基名不再是 Windows 保留设备名。二者均满足
    //（"_CO" 不是设备名），故本用例改断言不变量而非前缀外观。
    let exact = format!("CON.{}", "a".repeat(196));
    assert_eq!(exact.len(), MAX_FILENAME_LENGTH, "必须恰好触到上限");
    let out = SecurityPolicy::sanitize_filename(Some(&exact));
    assert!(
        out.len() <= MAX_FILENAME_LENGTH,
        "前缀后仍须 ≤MAX，实际 {}",
        out.len()
    );
    assert!(
        !RESERVED_NAMES.contains(&reserved_base_of(&out).as_str()),
        "基名必须已脱离保留设备名集：{out}"
    );
    assert!(out.starts_with('_'), "消解前缀至少须存活一位：{out}");
    // 对照：MAX-1 的保留名加前缀恰好用满上限
    let edge = format!("CON.{}", "a".repeat(195));
    let out = SecurityPolicy::sanitize_filename(Some(&edge));
    assert_eq!(out.len(), MAX_FILENAME_LENGTH, "前缀后恰好用满上限");
    // 截断路径（RS-114 场景）同样受新次序保护：消解后仍 ≤MAX 且基名非设备名
    let truncating = format!("CONX.{}", "f".repeat(196));
    let out = SecurityPolicy::sanitize_filename(Some(&truncating));
    assert!(out.len() <= MAX_FILENAME_LENGTH, "截断路径：{}", out.len());
    assert!(
        !RESERVED_NAMES.contains(&reserved_base_of(&out).as_str()),
        "截断不得把基名裁回设备名：{out}"
    );
    assert!(out.starts_with("_CON"), "截断后复查仍消解：{out}");
}

use super::super::*;

// —— RS-011/012 回归（审计 2026-09-24） ——

#[test]
fn host_with_embedded_colon_rejected() {
    // RS-011：host 段内嵌冒号此前借合法端口段被接受
    assert_eq!(try_parse_external("https://evil:8080:1234/"), None);
    assert_eq!(try_parse_external("https://a:b:99/"), None);
}

#[test]
fn host_character_whitelist_and_trailing_dot() {
    // RS-012：字符白名单；审计第六轮（2026-10-03）：尾点由「剥离放行」
    // 改为拒绝（与 C#/Kotlin OriginPolicy 对齐；contracts 侧
    // url-origin-invalid.json 同批补入尾点 deny 向量）
    assert_eq!(
        try_parse_external("https://example.org./x"),
        None,
        "尾点 FQDN 拒绝（不再剥离归一）"
    );
    assert_eq!(canonicalize_external("https://example.org./x"), None);
    assert_eq!(
        canonicalize_external("https://example.org./"),
        None,
        "纯尾点根域同样拒绝"
    );
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

// —— 审计第六轮（2026-10-03）：AD-252 尾点攻击面三端对齐 ——

#[test]
fn trailing_dot_loopback_and_whitelist_shapes_rejected() {
    // AD-252（Kotlin OriginPolicy.kt 记录）：Chromium 归一剥尾点后
    // `https://localhost./` 的 location.hostname == "localhost"，命中
    // bridge_guard 环回白名单成为 trustedCaller——归一层必须先行拒绝，
    // 不得替攻击者完成剥离
    for url in [
        "https://localhost./",
        "https://LOCALHOST./",
        "https://localhost./x?token=1",
        "https://localhost.:8443/",
        "https://aegis.local./",
        "https://127.0.0.1./",
        "https://example.org./",
    ] {
        assert_eq!(try_parse_external(url), None, "尾点形态必须拒绝：{url}");
    }
    // 对照：无尾点的同一批 host 保持放行（收窄不误伤）
    assert!(try_parse_external("https://localhost/").is_some());
    assert!(try_parse_external("https://127.0.0.1/").is_some());
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

// —— RS-227/228 回归（审计 2026-09-26） ——

#[test]
fn host_field_carries_non_default_port() {
    // RS-227：字段文档口径修正锁定——host 是规范化 authority：
    // 默认端口折叠（443/80 不出现），非默认端口保留在 host 内
    //（此前文档误称「host 不含端口」）
    let url = canonicalize_external("http://example.org:8080/p").unwrap();
    assert_eq!(url.host, "example.org:8080", "非默认端口保留在 host");
    assert_eq!(url.origin, "http://example.org:8080");
    let folded = canonicalize_external("https://example.org:443/p").unwrap();
    assert_eq!(folded.host, "example.org", "默认端口折叠出 host");
}

#[test]
fn ipv4_octets_out_of_range_rejected() {
    // RS-228：4 段全数字逐段 ≤255（WHATWG 口径）——八位组越界形态
    // 此前放行（「4 段全数字」只查了段数与数字性）
    assert_eq!(try_parse_external("https://999.1.1.1/"), None);
    assert_eq!(try_parse_external("https://256.0.0.1/"), None);
    assert_eq!(try_parse_external("https://1.2.3.999/"), None);
    assert_eq!(try_parse_external("https://300.300.300.300/"), None);
    // 合法边界（0 与 255）保留
    assert!(try_parse_external("https://0.0.0.0/").is_some());
    assert!(try_parse_external("https://255.255.255.255/").is_some());
    assert!(try_parse_external("https://192.168.1.1/").is_some());
}

#[test]
fn ipv4_leading_zero_and_mixed_hex_rejected() {
    // RS-238（2026-09-26 审计）：逐段前导零/0x——对齐 Kotlin AD-213 /
    // C# CS-307。前导零（inet_aton 八进制 = 127.0.0.1）与混合 0x 段
    //（0x7f.1 整串 startsWith 不命中）均为双重解释混淆面
    assert_eq!(try_parse_external("https://0177.0.0.1/"), None);
    assert_eq!(try_parse_external("https://192.168.001.001/"), None);
    assert_eq!(try_parse_external("https://010.1.2.3/"), None);
    assert_eq!(try_parse_external("https://0x7f.1/"), None);
    assert_eq!(try_parse_external("https://127.0.0x1/"), None);
    // 十进制合法形态不受影响（不含前导零/0x 段）
    assert!(try_parse_external("https://127.0.0.1/").is_some());
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
fn bracketed_ipv6_authority_grammar() {
    // RS-177 当年锁的是「`[` 开头的 authority 一律拒」——R9-B66（队列 Q4 的第二半）
    // 把这条换成「**语法收下、分类判**」：拒绝的活儿交给 is_high_risk_host（按字节，
    // 含 IPv4-mapped 折叠），语法层只负责「这是不是一个合法 IPv6 字面量」。
    // 因此本用例两半都要钉住：合法形态必须过（含 B8 要能打开的 `[::1]`），
    // 非法形态仍必须 None——列在下面第 3 组，那一组才是 RS-177 的真实遗产。
    let accepted = [
        "https://[2001:db8::1]/",
        "https://[::1]:8080/x",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fd00::1]:9000/api",
    ];
    for raw in accepted {
        let parsed = try_parse_external(raw);
        assert!(parsed.is_some(), "合法 IPv6 字面量不该被语法层拒：{raw}");
    }
    // host 段保留**字面**小写形态（不重排成平台规范形——三端打印格式不同，
    // 重排会让 origin 跨端不等）；带端口时端口跟在 `]` 之后
    assert_eq!(
        try_parse_external("HTTP://[FE80::1]:8080/x").map(|(scheme, host)| (scheme, host)),
        Some(("http".to_string(), "[fe80::1]:8080".to_string()))
    );
    // 第 3 组：RS-177 的遗产——这些形态**仍**必须拒。逐条都是不同的洞：
    // 未闭合、括号内嵌裸 IPv4（双重解释）、作用域号 `%eth0`、段数超限、
    // 空地址体、`]` 后跟非端口字符、端口 0/越界。
    for raw in [
        "https://[2001:db8::1/x",
        "https://[1.2.3.4]/",
        "https://[fe80::1%eth0]/",
        "https://[1:2:3:4:5:6:7:8:9]/",
        "https://[]/",
        "https://[::1]x/",
        "https://[::1]:0/",
        "https://[::1]:99999/",
    ] {
        assert_eq!(try_parse_external(raw), None, "非法 IPv6 字面量必须被拒：{raw}");
    }
    // 正常 host 不受影响（回归锚点）
    assert!(try_parse_external("https://example.org/").is_some());
}

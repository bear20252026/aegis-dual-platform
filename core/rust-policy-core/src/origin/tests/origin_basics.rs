use super::super::*;

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

// —— RS-289 回归（2026-10-02 审计）：path 不归一契约 ——

#[test]
fn canonical_parameters_do_not_normalize_dot_segments_or_percent_encoding() {
    // RS-289：path 段不做点段折叠 / 百分号解码归一（RFC 3986 的
    // remove_dot_segments 与 percent-decoding 均不执行）——同一逻辑
    // 资源的两种拼写产出不同 canonical_parameters（授权绑定按字面
    // 区分）。三端（Rust/C#/Kotlin）同步归一成本高，本轮锁定
    // 「不归一」口径；变更须经跨端契约评审同步三端，不得单端先行
    let dot = canonicalize_external("https://example.com/a/../b").unwrap();
    assert_eq!(dot.canonical_parameters, "/a/../b", "点段不折叠");
    let pct = canonicalize_external("https://example.com/%61%62").unwrap();
    assert_eq!(pct.canonical_parameters, "/%61%62", "百分号编码不解码");
    let dbl = canonicalize_external("https://example.com//double").unwrap();
    assert_eq!(dbl.canonical_parameters, "//double", "双斜杠原样保留");
    // 对照：scheme/host 归一仍生效（origin 侧既有口径不受影响）
    assert_eq!(pct.origin, "https://example.com");
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

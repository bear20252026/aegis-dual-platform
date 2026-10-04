use super::super::*;

// —— 审计第六轮（2026-10-03）：scheme 提取失败 fail-closed ——

#[test]
fn missing_or_empty_scheme_is_not_valid() {
    // 错误→ALLOW 修正：None/空 scheme 是提取失败面，不是「相对 URL 即
    // 放行」的证据；白名单判定只在拿到真实 scheme 后才成立
    assert!(!SecurityPolicy::is_valid_navigation_scheme(None));
    assert!(!SecurityPolicy::is_valid_navigation_scheme(Some("")));
    assert!(!SecurityPolicy::is_valid_navigation_scheme(Some(" ")));
    // 白名单内 scheme 仍放行（回归锚点）
    assert!(SecurityPolicy::is_valid_navigation_scheme(Some("https")));
    // 危险黑名单口径不变（空/None 仍非危险）
    assert!(!SecurityPolicy::is_dangerous_external_scheme(None));
    assert!(!SecurityPolicy::is_dangerous_external_scheme(Some("")));
}

// —— 审计第六轮（2026-10-03/04）：本机/私网主机判定 ——

#[test]
fn local_and_private_hosts_are_recognized() {
    for host in [
        "localhost",
        "127.0.0.1",
        "127.2.3.4", // 127/8 整段环回
        "0.0.0.0",
        "10.1.2.3",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254", // 云元数据地址
    ] {
        assert!(
            SecurityPolicy::is_local_or_private_host(host),
            "{host} 必须判为本机/私网"
        );
    }
}

#[test]
fn public_and_lookalike_hosts_are_not_flagged() {
    for host in [
        "172.15.0.1", // 172.16/12 边界外
        "172.32.0.1",
        "169.253.1.1", // 非链路本地
        "169.255.1.1",
        "8.8.8.8",
        "example.org",
        "localhost.evil.test", // 前缀相似名
        "evil-localhost",
        "127.0.0.1.evil.test",
        "",
        "1.2.3",     // 段数不足
        "1.2.3.4.5", // 段数过多
    ] {
        assert!(
            !SecurityPolicy::is_local_or_private_host(host),
            "{host} 不应被判为本机/私网"
        );
    }
}

#[test]
fn predicate_requires_pre_lowered_host_and_no_port() {
    // 本函数入参必须是 canonicalize_external 产出的**小写、已剥端口** host。
    // 两条前提不成立即漏判——RS-227 口径下 CanonicalExternalUrl.host 保留
    // 非默认端口，直接传 "127.0.0.1:8080" 会因末段 "1:8080" 解析失败而
    // 判为非本机（第六轮开发期实测到的绕过，调用方必须先 split(':') 取首段）。
    assert!(!SecurityPolicy::is_local_or_private_host("LOCALHOST"));
    assert!(!SecurityPolicy::is_local_or_private_host("127.0.0.1:8080"));
    assert!(SecurityPolicy::is_local_or_private_host("localhost"));
    assert!(SecurityPolicy::is_local_or_private_host("127.0.0.1"));
}

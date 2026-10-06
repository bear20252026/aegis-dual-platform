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
fn high_risk_hosts_are_recognized() {
    for host in [
        "0.0.0.0",
        "169.254.169.254", // 云元数据地址
        // 审计第七轮 R7-RS-05（2026-10-04）：补齐至 C# 孪生 UrlSafety.IsPublicIp
        // 的四段——纯函数级边界锚（端到端断言在 native-navigation-decision 向量）
        "100.100.100.200", // 阿里云元数据端点（100.64.0.0/10 CGNAT）
        "100.64.0.1",      // CGNAT 下边界
        "100.127.255.254", // CGNAT 上边界
        "192.0.2.1",       // TEST-NET-1
        "198.51.100.1",    // TEST-NET-2 下界（B9：C# 孪生早已覆盖）
        "198.51.100.254",  // TEST-NET-2 上界
        "203.0.113.7",     // TEST-NET-3（核心此前判公网，段集跨端不一致）
        "198.18.0.1",      // 基准段下边界
        "198.19.255.254",  // 基准段上边界
        "224.0.0.1",       // 组播
        "255.255.255.255", // 受限广播
    ] {
        assert!(
            SecurityPolicy::is_high_risk_host(host),
            "{host} 必须判为高危主机"
        );
    }
}

#[test]
fn public_and_lookalike_hosts_are_not_flagged() {
    for host in [
        // 第七轮 B8 裁决（本机与内网必须能打开）第八轮 B9 落进核心：以下形态
        // 曾在高危集里，现在必须判非高危——回归此断言即红
        "localhost",
        "127.0.0.1",
        "127.2.3.4",
        "10.1.2.3",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "192.168.1.1:8080",
        "172.15.0.1", // 172.16/12 边界外
        "172.32.0.1",
        "169.253.1.1", // 非链路本地
        "169.255.1.1",
        "8.8.8.8",
        "example.org",
        "localhost.evil.test", // 前缀相似名
        "evil-localhost",
        "127.0.0.1.evil.test",
        // R7-RS-05 段集的逐段左右对照（缺一即"整段扩大化"式过度收紧无人可抓）
        "100.63.255.254",  // CGNAT 下界之外
        "100.128.0.1",     // CGNAT 上界之外
        "192.0.1.254",     // TEST-NET-1 前邻
        "192.0.3.1",       // TEST-NET-1 后邻（第三段必须精确为 2）
        "198.51.99.254",   // TEST-NET-2 前邻
        "198.51.101.1",    // TEST-NET-2 后邻（第三段必须精确为 100）
        "203.0.112.254",   // TEST-NET-3 前邻
        "203.0.114.1",     // TEST-NET-3 后邻
        "198.17.255.254",  // 基准段前邻
        "198.20.0.1",      // 基准段后邻
        "223.255.255.254", // 组播段前邻
        "93.184.216.34",   // 真实公网
        "",
        "1.2.3",     // 段数不足
        "1.2.3.4.5", // 段数过多
    ] {
        assert!(
            !SecurityPolicy::is_high_risk_host(host),
            "{host} 不应被判为高危主机"
        );
    }
}

#[test]
fn predicate_requires_pre_lowered_host_and_no_port() {
    // 本函数入参必须是 canonicalize_external 产出的**小写、已剥端口** host。
    // 两条前提不成立即漏判——RS-227 口径下 CanonicalExternalUrl.host 保留
    // 非默认端口，直接传 "169.254.169.254:8080" 会因末段 "254:8080" 解析失败
    // 而判为非高危（第六轮开发期实测到的绕过，调用方必须先 split(':') 取首段，
    // 见 ffi/broker.rs 的 policy_host_of）。示例宿主改用元数据地址：回环与
    // localhost 名按第七轮 B8 裁决本就不判高危，拿它们证不了这条警示。
    assert!(!SecurityPolicy::is_high_risk_host("169.254.169.254:8080"));
    assert!(SecurityPolicy::is_high_risk_host("169.254.169.254"));
    assert!(!SecurityPolicy::is_high_risk_host("LOCALHOST"));
    assert!(!SecurityPolicy::is_high_risk_host("localhost"));
}

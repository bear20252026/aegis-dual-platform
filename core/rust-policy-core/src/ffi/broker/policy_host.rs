//! 内容判定用的 host 口径（R9-B66 从 `ffi/broker.rs` 拆出）。
//!
//! 拆文件的理由不是行数：这条口径的两种错法（剥多、剥少）都会让下游分类给出
//! 「看起来对」的结果——只有把取 host 与分类放在一起断言才看得见。

/// 内容判定用的 host 口径单源（evaluate 与 consume 复判共用，R7-RS-01/R7-RS-02）：
/// **剥去端口**的纯主机名。
///
/// CanonicalExternalUrl.host 依 RS-227 口径保留非默认端口（:8080 形态实证在
/// host 内），直接拿它比对会同时制造两个绕过：
///   ① 黑名单条目 `bad.example` 匹配不上 `bad.example:8443`；
///   ② 高危判定把 `169.254.169.254:8080` 当成非高危（split('.') 末段
///      "254:8080" 解析失败）而放行。
/// IPv6 字面量自 R9-B66 起被归一层**收下**，所以方括号形态必须单独走：端口在
/// `]` 之后，split(':') 取首段会把 `[::1]:8080` 截成 `[`——既不是地址也不是
/// 域名，于是本机回环被判高危（B8 裁决不可回退）。这里**保留方括号**返回：
/// `is_high_risk_host` 靠 `[` 前缀识别 IPv6 分支，剥掉括号会让它落回
/// 「split(':') 取首段」，`[fe80::1]` 因此被读成 `fe80` 判成公网（绕过）。
/// host 永不为空（归一层已拒空）。
pub(crate) fn policy_host_of(canonical: &crate::origin::CanonicalExternalUrl) -> &str {
    if !canonical.host.starts_with('[') {
        return canonical
            .host
            .split(':')
            .next()
            .unwrap_or(canonical.host.as_str());
    }
    match canonical.host.find(']') {
        Some(close) => &canonical.host[..=close],
        // 语法层保证进不到这里；真到了就原样交给判定函数（它按 fail-closed 处理）
        None => canonical.host.as_str(),
    }
}

#[cfg(test)]
mod tests {
    use super::policy_host_of;
    use crate::origin::canonicalize_external;
    use crate::security_policy::SecurityPolicy;

    fn host_of(raw: &str) -> String {
        let canonical =
            canonicalize_external(raw).unwrap_or_else(|| panic!("{raw} 应当被归一层收下"));
        policy_host_of(&canonical).to_string()
    }

    #[test]
    fn port_is_stripped_for_names_and_ipv4() {
        assert_eq!(host_of("https://bad.example:8443/x"), "bad.example");
        assert_eq!(host_of("https://169.254.169.254:8080/x"), "169.254.169.254");
        assert_eq!(host_of("https://example.com/x"), "example.com");
    }

    #[test]
    fn bracketed_ipv6_keeps_brackets_and_drops_port() {
        assert_eq!(host_of("http://[::1]:9000/probe"), "[::1]");
        assert_eq!(host_of("http://[fe80::1]/"), "[fe80::1]");
        // 归一层只做小写折叠、不重排地址文本（三端各自打印 IPv6 的形态不同，
        // origin 相等性要求这里也保持字面量）——`0DB8` 变 `0db8`，不变成 `db8`
        assert_eq!(host_of("https://[2001:0DB8::1]/x"), "[2001:0db8::1]");
    }

    /// 上面两条的形状不是排版要求：剥掉括号（`fe80` 判成公网）与不剥端口
    /// （`[` 判成高危）都能让某一条向量"过"，只有把 host 交给真分类器才现形。
    #[test]
    fn host_shape_drives_the_classifier() {
        assert!(
            SecurityPolicy::is_high_risk_host(&host_of("http://[fe80::1]:8080/")),
            "链路本地带端口必须仍判高危"
        );
        assert!(
            SecurityPolicy::is_high_risk_host(&host_of("https://169.254.169.254:8080/x")),
            "云元数据带端口必须仍判高危"
        );
        assert!(
            !SecurityPolicy::is_high_risk_host(&host_of("http://[::1]:9000/probe")),
            "B8 裁决：本机回环不判高危"
        );
        assert!(
            !SecurityPolicy::is_high_risk_host(&host_of("http://[fd00::1]/api")),
            "ULA 内网不判高危"
        );
    }
}

//! Origin/URL canonicalization（蓝图阶段 F 第二推荐项）。
//!
//! 与 contracts/vectors/url-origin-valid|invalid.json 一致（http/https 放行——
//! data:/blob:/javascript:/userinfo/控制字符/无 host/超长拒绝——P0-01 同语义）。
//! 审计第六轮（2026-10-03）：尾点 host（`https://example.org./`）纳入拒绝集——
//! 三端（Rust/C#/Kotlin）归一口径统一，剥尾点归一即 AD-252 攻击面本身。
//! 纯函数——无 I/O。

/// 已规范化的外部 URL；fragment 不参与副作用授权绑定。
///
/// RS-190（审计 2026-09-25）：字段级文档——本结构是授权绑定的载体，
/// 各字段语义由注释锁定，跨端（C#/Kotlin/Python）消费方据此对齐。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalExternalUrl {
    /// 小写 scheme——仅 "http" / "https"（其余在 canonicalize_external 拒绝）。
    pub scheme: String,
    /// 规范化 authority（小写 host + 非默认端口）——RS-227（2026-09-26
    /// 审计）口径修正：默认端口（80/443）不出现在 host；**非默认端口保留
    /// 在 host 内**（host: canonical_authority，此前文档误称「不含端口」——
    /// 实现与测试均证明 :8080 形态保留）。纯 host（无端口）由 origin
    /// 去掉 scheme:// 前缀自行截取，或经 host.split(':') 取首段。
    pub host: String,
    /// 授权绑定 origin（`scheme://host[:port]`）——默认端口省略，非默认
    /// 端口保留。授权相等性以此字段为准。
    pub origin: String,
    /// 规范化 path + query（fragment 已剥离——fragment 不参与副作用授权，
    /// `#` 之后内容不进入绑定比较）。
    pub canonical_parameters: String,
}

/// 解析并规范化外部 URL（仅 http/https——非法返回 None——fail-closed）。
pub fn canonicalize_external(raw: &str) -> Option<CanonicalExternalUrl> {
    const MAX_URL_LENGTH: usize = 8192;
    if raw.is_empty() || raw.len() > MAX_URL_LENGTH {
        return None;
    }
    if raw
        .bytes()
        .any(|b| b < 0x20 || b == 0x7f || b.is_ascii_whitespace())
    {
        return None;
    }
    let (raw_scheme, rest) = raw.split_once("://")?;
    let scheme = raw_scheme.to_ascii_lowercase();
    if scheme != "http" && scheme != "https" {
        return None; // 拒绝 data:/blob:/javascript:/file: 等（url-origin-invalid 向量）
    }
    let authority = rest.split(['/', '?', '#']).next()?;
    if authority.is_empty() || authority.contains('@') || authority.starts_with('[') {
        return None; // 无 host / userinfo（url-origin-invalid 向量）
    }
    let (raw_host, port) = if let Some((host, port)) = authority.rsplit_once(':') {
        if host.is_empty() {
            return None;
        }
        // RS-011（审计 2026-09-24）：host 段拒内嵌冒号——此前 rsplit_once
        // 取最后一段当端口，"host:8080:1234" 以 host="host:8080" 被接受
        //（合法端口掩盖非法 authority）
        if host.contains(':') {
            return None;
        }
        // 非法端口拒绝（contracts/vectors/url-origin-invalid——https://host:99999
        // ——u16 范围校验——WHATWG 同语义——P0-01）
        let Ok(port_num) = port.parse::<u16>() else {
            return None;
        };
        if port_num == 0 {
            return None;
        }
        (host, Some(port_num))
    } else {
        (authority, None)
    };
    let host = raw_host.to_ascii_lowercase();
    if host.is_empty() {
        return None;
    }
    // RS-012（审计 2026-09-24）：host 字符白名单——剥离后仅允许
    // [a-z0-9.-]（xn-- punycode 亦在集内），其余字符（下划线/空格/控制符
    // 等）一律拒绝。
    // 审计第六轮（2026-10-03）：尾点 host 由「剥离归一」改为**拒绝**——
    // 与 C# OriginPolicy.IsValidHost（`host.EndsWith(".")` 即 false）/
    // Kotlin OriginPolicy.isAcceptedHostShape（`!host.endsWith(".")`）
    // 口径一致（RS-012 注释曾称「与 C# 口径一致」却做了反向归一，本轮
    // 更正）。理由：Chromium 归一化剥尾点，`https://localhost./` 在内核
    // 侧呈现 `location.hostname == "localhost"` 并命中 bridge_guard 环回
    // 白名单（AD-252 记录的攻击面）——归一层剥尾点正是该攻击本身，
    // 而非合法 FQDN 根表示的宽容
    if host.ends_with('.') {
        return None; // 尾点 host（含 "." 单点形态）拒绝
    }
    if host.is_empty()
        || host.starts_with('.')
        || host.contains("..")
        || !host
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
    {
        return None;
    }
    // PY-071/072（审计 2026-09-25）：非点分十进制 IPv4 编码拒绝——整数
    //（2130706433）/0x 十六进制（0x7f000001）/简写（127.1）形态 OS 解析器
    // 均接受，同一 URL 双重解释是混淆面——对齐 C# UrlSafety/OriginPolicy
    // 口径（contracts/vectors/url-origin-invalid PY-071/072 向量）。
    // 全数字段且段数 ≠ 4 一律拒绝（4 段 = 合法点分 IPv4 字面量，保留）；
    // 0x 十六进制 host 单独拒绝
    let segments: Vec<&str> = host.split('.').collect();
    let all_digit_segments = segments
        .iter()
        .all(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()));
    if segments.len() != 4 && all_digit_segments {
        return None;
    }
    // RS-228（2026-09-26 审计）：4 段全数字时逐段 ≤255（WHATWG IPv4 解析
    // 器口径）——此前只看「4 段全数字」即放行，999.1.1.1/256.0.0.1 等
    // 八位组越界形态混过（跨端向量同步见 contracts 侧登记，Rust 先行收紧）
    if segments.len() == 4
        && all_digit_segments
        && segments
            .iter()
            .any(|s| !s.parse::<u16>().is_ok_and(|v| v <= 255))
    {
        return None;
    }
    // RS-238（2026-09-26 审计）：逐段前导零/0x 判定——对齐 Kotlin AD-213/
    // C# CS-307 口径。此前整串 startsWith("0x") 对 "0x7f.1" 混合段判 false、
    // "0177.0.0.1" 四段全数字即放行（inet_aton 系按八进制解释 = 127.0.0.1，
    // Chromium WHATWG 归一后可命中本地白名单——双重解释混淆面）。
    let has_hex_segment = segments.iter().any(|s| {
        s.len() > 2
            && s.starts_with("0x")
            && s[2..]
                .bytes()
                .any(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    });
    let has_leading_zero_segment = segments
        .iter()
        .any(|s| s.len() > 1 && s.starts_with('0') && s.bytes().all(|b| b.is_ascii_digit()));
    if has_hex_segment || has_leading_zero_segment {
        return None;
    }
    if host.starts_with("0x")
        && host[2..]
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return None; // 0x 十六进制 host
    }
    let host = host.to_string();
    let canonical_authority = match port {
        Some(value)
            if !((scheme == "https" && value == 443) || (scheme == "http" && value == 80)) =>
        {
            format!("{host}:{value}")
        }
        _ => host,
    };
    let suffix = &rest[authority.len()..];
    // RS-059（审计 2026-09-25）：split 恒产生首元素——unwrap_or_default
    // 属冗余解包，改 split_once 显式表达「无 # 即整段」语义
    let without_fragment = suffix.split_once('#').map_or(suffix, |(before, _)| before);
    // RS-289（2026-10-02 审计）：path 段**不做归一**（点段折叠 / 百分号
    // 解码均不执行）——同一逻辑资源的两种拼写产出不同 canonical_parameters
    //（授权绑定按字面区分）。三端（Rust/C#/Kotlin）同步归一成本高，本轮
    // 显式锁定「不归一」口径（契约测试 canonical_parameters_do_not_normalize_
    // dot_segments_or_percent_encoding）；如需变更须经跨端契约评审同步三端，
    // 不得单端先行
    let canonical_parameters = match without_fragment {
        "" => "/".to_string(),
        query if query.starts_with('?') => format!("/{query}"),
        path => path.to_string(),
    };
    // RS-060（审计 2026-09-25）：origin 单次 format 构造后整体 move——
    // 此前 scheme.clone() + canonical_authority.clone() 双 clone
    let origin = format!("{scheme}://{canonical_authority}");
    Some(CanonicalExternalUrl {
        scheme,
        host: canonical_authority,
        origin,
        canonical_parameters,
    })
}

/// 解析外部 URL 的兼容入口（仅返回规范化 scheme 与 authority）。
pub fn try_parse_external(raw: &str) -> Option<(String, String)> {
    canonicalize_external(raw).map(|url| (url.scheme, url.host))
}

#[cfg(test)]
mod tests;

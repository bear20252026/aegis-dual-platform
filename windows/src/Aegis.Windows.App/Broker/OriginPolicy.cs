namespace Aegis.Windows.Broker;

using System;
using System.Globalization;
using System.Linq;

/// <summary>Origin/URL 策略（阶段 C——Broker 导航决策核心——与 contracts/vectors 对齐）。
/// 外部导航仅 http/https；拒绝 data:/blob:/javascript:/userinfo/控制字符/空白/
/// 无 host/非法端口/超长/尾点 host/IDN bidi 混排（url-origin-invalid 向量——契约一致）。</summary>
public static class OriginPolicy
{
    public const int MaxUrlLength = 8192;
    public const int MaxHostLength = 253;

    public static bool TryParseExternal(string raw, out Uri uri)
    {
        uri = null!;
        if (string.IsNullOrEmpty(raw) || raw.Length > MaxUrlLength)
            return false;
        foreach (var ch in raw)
        {
            if (ch < 0x20 || ch == 0x7f || char.IsWhiteSpace(ch))
                return false;
        }
        if (!Uri.TryCreate(raw, UriKind.Absolute, out var u))
            return false;
        if (u.Scheme != Uri.UriSchemeHttp && u.Scheme != Uri.UriSchemeHttps)
            return false;
        // PY-076：authority 含 '@'（含空密码形态 "https://@host/"——.NET
        // 解析后 UserInfo 为空串，u.UserInfo 检查不可见）一律拒绝——与 Rust
        // origin.rs / Kotlin rawUserInfo 口径一致
        var schemeEnd = raw.IndexOf("://", StringComparison.Ordinal);
        var authority = raw[(schemeEnd + 3)..];
        var authorityEnd = authority.IndexOfAny(new[] { '/', '?', '#' });
        if (authorityEnd >= 0)
            authority = authority[..authorityEnd];
        if (authority.Contains('@', StringComparison.Ordinal))
            return false;
        if (!string.IsNullOrEmpty(u.UserInfo))
            return false;
        if (string.IsNullOrEmpty(u.Host))
            return false;
        if (!IsValidHost(u.Host))
            return false;
        uri = u;
        return true;
    }

    /// <summary>host 白名单式校验：剥 IPv6 方括号后按标签校验——字母/数字/
    /// 连字符/点（或 IPv6 字面量）；拒绝尾点、空白折叠、Unicode 控制符与
    /// bidi 混排字符（IDN 欺骗面——显示同形不同址）。</summary>
    private static bool IsValidHost(string host)
    {
        if (host.Length == 0 || host.Length > MaxHostLength)
            return false;
        // .NET Uri.Host 对 IPv6 字面量去方括号；DnsSafeHost 保留——按原串判断
        var isIpv6 = host.Contains(':', StringComparison.Ordinal);
        if (isIpv6)
        {
            // 仅允许十六进制/冒号/点（v4-mapped 尾段）
            foreach (var ch in host)
            {
                var isHex = char.IsAsciiDigit(ch)
                    || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F');
                if (!(isHex || ch == ':' || ch == '.'))
                    return false;
            }
            return true;
        }
        if (host.EndsWith(".", StringComparison.Ordinal))
            return false;  // 尾点 host（"example.com."）——规范化歧义面
        foreach (var ch in host)
        {
            // 非 ASCII（含 punycode 前的 IDN 与 bidi 字符）经 .NET Uri 已转
            // punycode（xn--）；仍显式拒绝非 DNS 安全字符集之外的残留
            if (!(char.IsAsciiLetterOrDigit(ch) || ch == '-' || ch == '.'))
                return false;
        }
        foreach (var label in host.Split('.'))
        {
            if (label.Length == 0 || label.Length > 63)
                return false;
            if (label.StartsWith('-') || label.EndsWith('-'))
                return false;
        }
        // PY-071/072（审计 2026-09-25）：非点分十进制 IPv4 编码拒绝——整数
        //（2130706433）/0x 十六进制/简写（127.1）OS 解析器均接受，双重解释
        // 混淆面。全数字段且段数 ≠ 4 拒（4 段 = 合法点分 IPv4，保留）；
        // 与 Rust origin.rs / Kotlin OriginPolicy 口径一致
        var segments = host.Split('.');
        var lower = host.ToLowerInvariant();
        if (segments.Length != 4 && segments.All(s => s.Length > 0 && s.All(char.IsAsciiDigit)))
            return false;
        if (lower.StartsWith("0x") && lower[2..].All(c => char.IsAsciiDigit(c) || (c >= 'a' && c <= 'f')))
            return false;
        return true;
    }
}

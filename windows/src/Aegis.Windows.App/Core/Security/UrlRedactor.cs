namespace Aegis.Windows.Core.Security;

using System;

/// <summary>CS-070（审计 2026-09-25）：审计/日志用 URL 脱敏单源——
/// 此前 BrowserPolicyBroker 与 HostWebView 各持一份逐行相同实现（漂移面）。
/// 丢弃 query/fragment（token、搜索词等敏感串不落盘），超长截断。
/// CS-296（2026-09-26 审计）：回退截断分支吸收代理对安全逻辑（此前仅
/// Broker 私有副本有——共享单源硬切可产生孤立代理落审计，双源收敛）。
/// CS-337（2026-10-01 审计）：authority 组装改 Scheme + Uri.Authority——
/// GetLeftPart(UriPartial.Authority) 含 userinfo（https://token@host/ 被
/// 拒后凭据完整落 security.log）；Uri.Authority 按实验（.NET 10）不含
/// userinfo 且 IPv6 保留方括号。</summary>
public static class UrlRedactor
{
    private const int MaxRawLength = 256;

    public static string Redact(string? url)
    {
        if (string.IsNullOrEmpty(url))
            return string.Empty;
        if (Uri.TryCreate(url, UriKind.Absolute, out var uri) && !string.IsNullOrEmpty(uri.Host))
            return uri.Scheme + Uri.SchemeDelimiter + uri.Authority + uri.AbsolutePath;
        if (url.Length <= MaxRawLength)
            return url;
        // CS-212：代理对安全截断（URL 含 emoji 时硬切产生孤立代理落审计）
        var cut = MaxRawLength;
        if (char.IsHighSurrogate(url[cut - 1]))
            cut--;
        return url[..cut] + "…";
    }
}

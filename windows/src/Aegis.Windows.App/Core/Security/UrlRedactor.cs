namespace Aegis.Windows.Core.Security;

using System;

/// <summary>CS-070（审计 2026-09-25）：审计/日志用 URL 脱敏单源——
/// 此前 BrowserPolicyBroker 与 HostWebView 各持一份逐行相同实现（漂移面）。
/// 丢弃 query/fragment（token、搜索词等敏感串不落盘），超长截断。</summary>
public static class UrlRedactor
{
    public static string Redact(string? url)
    {
        if (string.IsNullOrEmpty(url))
            return string.Empty;
        if (Uri.TryCreate(url, UriKind.Absolute, out var uri) && !string.IsNullOrEmpty(uri.Host))
            return uri.GetLeftPart(UriPartial.Authority) + uri.AbsolutePath;
        return url.Length > 256 ? url[..256] + "…" : url;
    }
}

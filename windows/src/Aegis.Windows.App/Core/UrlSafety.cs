namespace Aegis.Windows.Core;

using System;
using System.Net;

/// <summary>外部导航 URL 安全判定（新窗口/新标签打开入口共用——ADR-002 默认拒绝）。
/// 约束：仅 http/https；发送/打开前一并拒绝 localhost、回环、私有与保留地址
/// （杜绝把内网/保留地址暴露给页面导航的面）。NTP/画板等受信虚拟主机不在此
/// 通道（内网外部链接）。纯静态判定，全量可单测。</summary>
public static class UrlSafety
{
    /// <summary>是否为可安全打开的外部 http/https URL（公网 host）。</summary>
    public static bool IsPublicHttpUrl(string? url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return false;
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return false;
        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
            return false;
        if (string.IsNullOrEmpty(uri.Host))
            return false;
        return IsPublicHost(uri.Host);
    }

    /// <summary>host 是否属公网（非 localhost、回环、私有、链路本地、保留、组播）。</summary>
    public static bool IsPublicHost(string host)
    {
        var normalized = host.TrimEnd('.').ToLowerInvariant();
        // 主机名形式的本地/保留名
        if (normalized.Equals("localhost", StringComparison.Ordinal))
            return false;
        if (IPAddress.TryParse(normalized, out var address))
            return IsPublicIp(address);
        // 以 localhost/内网域名后缀结尾的本地名（如 foo.localhost）
        if (normalized.EndsWith(".localhost", StringComparison.Ordinal))
            return false;
        // 内网保留域名后缀
        if (normalized.EndsWith(".local", StringComparison.Ordinal)
            || normalized.EndsWith(".internal", StringComparison.Ordinal))
            return false;
        return true;
    }

    /// <summary>IP 地址是否公网（非回环/私有/链路本地/保留/组播/unspecified）。</summary>
    public static bool IsPublicIp(IPAddress address)
    {
        if (address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any)
            || address.Equals(IPAddress.Loopback) || address.Equals(IPAddress.IPv6Loopback))
            return false;
        if (IPAddress.IsLoopback(address))
            return false;
        if (address.IsIPv6LinkLocal || address.IsIPv6Multicast)
            return false;
        var bytes = address.GetAddressBytes();
        if (bytes.Length == 4)
        {
            var b0 = bytes[0];
            if (b0 == 0 || b0 == 10 || b0 == 127)
                return false;
            if (b0 == 169 && bytes[1] == 254)
                return false;  // 链路本地 169.254.0.0/16
            if (b0 == 172 && bytes[1] is >= 16 and <= 31)
                return false;  // 172.16.0.0/12
            if (b0 == 192 && bytes[1] == 168)
                return false;  // 192.168.0.0/16
            if (b0 == 100 && bytes[1] is >= 64 and <= 127)
                return false;  // 100.64.0.0/10 CGNAT
            if (b0 >= 224)
                return false;  // 组播/保留 224.0.0.0/4
            if (b0 == 255)
                return false;  // 广播 255.255.255.255
            return true;
        }
        if (bytes.Length == 16)
        {
            // IPv6 ULA fc00::/7 与 site-local fec0::/10 视作私网
            if (bytes[0] == 0xfc || bytes[0] == 0xfd || bytes[0] == 0xfe)
                return false;
            return true;
        }
        return false;
    }
}
namespace Aegis.Windows.Core;

using System;
using System.Collections.Concurrent;
using System.Linq;
using System.Net;

/// <summary>外部导航 URL 安全判定（新窗口/新标签打开入口共用——ADR-002 默认拒绝）。
/// 约束：仅 http/https；发送/打开前一并拒绝 localhost、回环、私有与保留地址
/// （杜绝把内网/保留地址暴露给页面导航的面）。NTP/画板等受信虚拟主机不在此
/// 通道（内网外部链接）。纯静态判定，全量可单测。</summary>
public static class UrlSafety
{
    private static readonly ConcurrentDictionary<string, (bool IsLocal, long StampMs)> LocalHostCache = new();
    private static readonly TimeSpan LocalHostCacheTtl = TimeSpan.FromSeconds(60);

    /// <summary>是否为可安全打开的外部 http/https URL（公网 host，或本机/回环/
    /// hosts 映射到本机的域名——后者为本地开发访问开放）。</summary>
    public static bool CanOpenHttpUrl(string? url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return false;
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return false;
        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
            return false;
        if (string.IsNullOrEmpty(uri.Host))
            return false;
        return IsPublicHost(uri.Host) || IsLocalHostOrResolvesLocalHost(uri.Host);
    }

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

    /// <summary>host 是否属公网（非 localhost、回环、私有、链路本地、保留、组播）。
    /// 非点分十进制 IPv4 编码（整数 2130706433 / 十六进制 0x7f000001 / 简写 127.1）
    /// 先规范化再判定——OS 解析器接受这些形态，本层此前判为"公网主机名"。</summary>
    public static bool IsPublicHost(string host)
    {
        var normalized = host.TrimEnd('.').ToLowerInvariant();
        // 主机名形式的本地/保留名
        if (normalized.Equals("localhost", StringComparison.Ordinal))
            return false;
        if (IPAddress.TryParse(normalized, out var address))
            return IsPublicIp(address);
        if (TryParseAlternateIpv4(normalized, out var altAddress))
            return IsPublicIp(altAddress);  // 整数/十六进制/简写编码的 IP 字面量
        // 以 localhost/内网域名后缀结尾的本地名（如 foo.localhost）
        if (normalized.EndsWith(".localhost", StringComparison.Ordinal))
            return false;
        // 内网保留域名后缀
        if (normalized.EndsWith(".local", StringComparison.Ordinal)
            || normalized.EndsWith(".internal", StringComparison.Ordinal))
            return false;
        return true;
    }

    /// <summary>解析非点分十进制 IPv4 编码（十进制整数 / 0x 十六进制 / 2-3 段
    /// 简写如 127.1 = 127.0.0.1）。非该类形态返回 false。</summary>
    private static bool TryParseAlternateIpv4(string host, out IPAddress address)
    {
        address = IPAddress.None;
        // 纯十进制整数（2130706433 → 127.0.0.1）
        if (host.Length > 0 && host.Length <= 10 && host.All(char.IsDigit))
        {
            return TryFromLong(long.Parse(host, System.Globalization.CultureInfo.InvariantCulture), out address);
        }
        // 0x 十六进制整数
        if (host.StartsWith("0x", StringComparison.Ordinal) && host.Length <= 10
            && host[2..].All(c => char.IsDigit(c) || (c >= 'a' && c <= 'f')))
        {
            return TryFromLong(Convert.ToInt64(host, 16), out address);
        }
        // 2/3 段简写（a.b / a.b.c → 缺省段补 0）
        var parts = host.Split('.');
        if (parts.Length is 2 or 3 && parts.All(p => p.Length > 0 && p.Length <= 3 && p.All(char.IsDigit)))
        {
            while (parts.Length < 4)
                parts = parts.Append("0").ToArray();
            if (IPAddress.TryParse(string.Join('.', parts), out var expanded))
            {
                address = expanded;
                return true;
            }
            return false;
        }
        return false;

        static bool TryFromLong(long value, out IPAddress addr)
        {
            addr = IPAddress.None;
            if (value < 0 || value > 0xFFFFFFFF)
                return false;
            addr = new IPAddress((uint)value);
            return true;
        }
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
        var raw = address.GetAddressBytes();
        // IPv4-mapped IPv6（::ffff:192.168.1.1）——按内嵌 IPv4 判定（此前
        // bytes[0]==0x00 被判"公网"，私网/回环绕过）
        if (raw.Length == 16 && raw[..10].All(b => b == 0) && raw[10] == 0xFF && raw[11] == 0xFF)
            return IsPublicIp(new IPAddress(raw[12..]));
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
            if (b0 == 192 && bytes[1] == 0 && bytes[2] == 2)
                return false;  // 192.0.2.0/24 TEST-NET（文档示例段）
            if (b0 == 198 && (bytes[1] == 18 || bytes[1] == 19))
                return false;  // 198.18.0.0/15 基准测试段
            if (b0 >= 224)
                return false;  // 组播/保留 224.0.0.0/4
            if (b0 == 255)
                return false;  // 广播 255.255.255.255
            return true;
        }
        if (bytes.Length == 16)
        {
            // IPv6 ULA fc00::/7（私网）
            if ((bytes[0] & 0xFE) == 0xFC)
                return false;
            // site-local fec0::/10
            if (bytes[0] == 0xFE && (bytes[1] & 0xC0) == 0xC0)
                return false;
            // 组播 ff00::/8（此前仅靠 IsIPv6Multicast 属性，首字节 0xfe 粗判
            // 同时漏判 ff 段——显式拦）
            if (bytes[0] == 0xFF)
                return false;
            // IPv4 兼容/映射残留 ::a.b.c.d（前置 96 位零 + 内嵌 IPv4）
            if (bytes[..12].All(b => b == 0) && bytes[12] != 0)
                return IsPublicIp(new IPAddress(bytes[12..]));
            return true;
        }
        return false;
    }

    /// <summary>host 是否为本机/回环/经 hosts 解析到本机的域名（放开本地开发访问）。
    /// 快路径命中显式本机名（localhost/.localhost/回环 IP）；否则做一次带缓存的
    /// DNS 解析——hosts 文件映射的本地域名将解析到回环地址而被判为本机。
    /// 安全权衡：允许导航/打开本机地址（导航仍经 broker 授权、无远程代码执行），
    /// 属用户明确要求的开发场景能力；DNS 结果按 host 缓存 60s 降低热路径开销。</summary>
    public static bool IsLocalHostOrResolvesLocalHost(string host)
    {
        var normalized = host.TrimEnd('.').ToLowerInvariant();
        if (normalized.Equals("localhost", StringComparison.Ordinal)
            || normalized.EndsWith(".localhost", StringComparison.Ordinal))
            return true;
        if (IPAddress.TryParse(normalized, out var ip))
            return IsLocalIp(ip);
        var now = Environment.TickCount64;
        if (LocalHostCache.TryGetValue(normalized, out var entry)
            && now - entry.StampMs < (long)LocalHostCacheTtl.TotalMilliseconds)
            return entry.IsLocal;
        var isLocal = false;
        try
        {
            foreach (var address in Dns.GetHostAddresses(normalized))
            {
                if (IsLocalIp(address))
                {
                    isLocal = true;
                    break;
                }
            }
        }
        catch (Exception)
        {
            isLocal = false;  // 解析失败 → 非本机
        }
        LocalHostCache[normalized] = (isLocal, now);
        // 缓存有界（此前只写入从不逐出——长期浏览大量 host 永久驻留）
        if (LocalHostCache.Count > 2000)
            LocalHostCache.Clear();
        return isLocal;
    }

    private static bool IsLocalIp(IPAddress address) =>
        address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any)
        || address.Equals(IPAddress.Loopback) || address.Equals(IPAddress.IPv6Loopback)
        || IPAddress.IsLoopback(address);
}
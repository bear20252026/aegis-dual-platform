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

    /// <summary>是否为可安全打开的外部 http/https URL（公网 host）。
    /// CS-313（2026-09-26 审计）：生产零调用（生产路径统一走 CanOpenHttpUrl
    /// ——本机开发访问同样放行）。保留原因：UrlSafetyTests/AuditRegressionTests
    /// 以本方法锁定"公网判定不含本机豁免"的纯公网口径（CanOpenHttpUrl 的
    /// 本机放行使其无法断言该分支）——注明保留，避免误删回归覆盖。</summary>
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
        // Uri.Host 对 IPv6 字面量保留方括号——剥离包裹后按 IP 字面量判定
        // （此前方括号形态整体落到"公网主机名"兜底：连链路本地/私网都放行）
        if (normalized.Length > 2 && normalized.StartsWith('[') && normalized.EndsWith(']'))
            normalized = normalized[1..^1];
        // CS-201：IPv6 zone-id 形态（fe80::1%25eth0）与未闭合方括号残留——
        // TryParse 失败时绝不可落到"公网主机名"兜底放行（链路本地逃逸面）
        if (normalized.Contains('%') || normalized.Contains('[') || normalized.Contains(']'))
            return false;
        // CS-307（2026-09-26 审计）：前导零八进制 IPv4（"0177.0.0.1"）。
        // CS-348（2026-10-01 审计·确定性实验统一口径）：.NET 10 实测
        // IPAddress.TryParse("0177.0.0.1") 与 Uri.TryCreate 均按 inet_aton
        // 八进制语义归一为 127.0.0.1（此前本注释称"按十进制解释为 177.0.0.1
        // 判公网放行"——与实验不符，OriginPolicy.cs 侧注释才是对的）。
        // 两防线分工：本层（公网判定）TryParseOctalIpv4 显式先行仍保留——
        // IPAddress 对八进制形态的解释是平台/版本敏感到实现细节，防御纵深
        // 不依赖它；OriginPolicy（导航白名单）对 raw authority 前置同判。
        // 不可解析的畸形数字段按非公网 fail-closed
        if (TryParseOctalIpv4(normalized, out var octalAddress))
            return IsPublicIp(octalAddress);
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
        // 0x 十六进制整数（Length>2：至少一位 hex 数字——"0x" 裸前缀会使
        // Convert.ToInt64 抛 FormatException，此前 host[2..] 空串 All() 恒真）
        if (host.StartsWith("0x", StringComparison.Ordinal) && host.Length > 2 && host.Length <= 10
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

    /// <summary>CS-307：4 段全数字且任一段含前导零的 IPv4 变体——OS 解析栈
    ///（inet_aton 语义）对前导零段按八进制解释（"0177.0.0.1" = 127.0.0.1）。
    /// 仅识别该形态；逐段八进制/十进制混合解析，畸形（非八进制数字/越界）
    /// 返回 false 由调用方 fail-closed 判非公网。</summary>
    private static bool TryParseOctalIpv4(string host, out IPAddress address)
    {
        address = IPAddress.None;
        var parts = host.Split('.');
        if (parts.Length != 4
            || !parts.All(p => p.Length > 0 && p.Length <= 4 && p.All(char.IsAsciiDigit))
            || !parts.Any(p => p.Length > 1 && p[0] == '0'))
            return false;  // 非本形态（普通点分十进制/域名走各自路径）
        var bytes = new byte[4];
        for (var i = 0; i < 4; i++)
        {
            var part = parts[i];
            // 前导零段按八进制（与 OS 语义一致）；无前导零段按十进制
            var isOctal = part.Length > 1 && part[0] == '0';
            if (isOctal && !part.All(c => c is >= '0' and <= '7'))
                return false;  // "0999" 类非法八进制——不可安全解释，拒绝
            var value = isOctal
                ? Convert.ToInt32(part, 8)
                : int.Parse(part, System.Globalization.CultureInfo.InvariantCulture);
            if (value is < 0 or > 255)
                return false;
            bytes[i] = (byte)value;
        }
        address = new IPAddress(bytes);
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
        var raw = address.GetAddressBytes();
        // IPv4-mapped IPv6（::ffff:192.168.1.1）——按内嵌 IPv4 判定（此前
        // bytes[0]==0x00 被判"公网"，私网/回环绕过）
        if (raw.Length == 16 && raw[..10].All(b => b == 0) && raw[10] == 0xFF && raw[11] == 0xFF)
            return IsPublicIp(new IPAddress(raw[12..]));
        // CS-315（2026-09-26 审计）：bytes 复用 raw——此前同一地址两次
        // GetAddressBytes（第二次分配纯冗余）
        var bytes = raw;
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

    /// <summary>CS-339（2026-10-01 审计）：只读缓存探测——绝不发起同步 DNS。
    /// 帧导航路径此前缓存未命中即在 UI 线程逐帧同步解析（恶意页嵌多个不可解析
    /// http iframe 即逐帧冻结 UI）。命中显式本机名/回环 IP 或既有缓存返回 true
    /// 并给出判定；未知返回 false——调用方须 fail-closed 取消并自行后台预热。</summary>
    public static bool TryGetCachedLocalHost(string host, out bool isLocal)
    {
        isLocal = false;
        var normalized = host.TrimEnd('.').ToLowerInvariant();
        if (normalized.Equals("localhost", StringComparison.Ordinal)
            || normalized.EndsWith(".localhost", StringComparison.Ordinal))
        {
            isLocal = true;
            return true;
        }
        if (IPAddress.TryParse(normalized, out var ip))
        {
            isLocal = IsLocalIp(ip);
            return true;
        }
        if (LocalHostCache.TryGetValue(normalized, out var entry)
            && Environment.TickCount64 - entry.StampMs < (long)LocalHostCacheTtl.TotalMilliseconds)
        {
            isLocal = entry.IsLocal;
            return true;
        }
        return false;  // 未命中——不同步解析（调用方 fail-closed + 后台预热）
    }

    /// <summary>CS-339 测试缝：预置 DNS 缓存（单测避免真实解析的时延/环境漂移）。</summary>
    internal static void SeedLocalHostCacheForTests(string host, bool isLocal) =>
        LocalHostCache[host.TrimEnd('.').ToLowerInvariant()] = (isLocal, Environment.TickCount64);

    private static bool IsLocalIp(IPAddress address) =>
        address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any)
        || address.Equals(IPAddress.Loopback) || address.Equals(IPAddress.IPv6Loopback)
        || IPAddress.IsLoopback(address);
}
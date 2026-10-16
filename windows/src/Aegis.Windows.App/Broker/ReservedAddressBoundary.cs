namespace Aegis.Windows.Broker;

using System;
using System.Globalization;
using System.Linq;
using System.Net;

/// <summary>保留地址边界（四类出口共用的**唯一谓词源**：顶层导航、授权消费、
/// 子资源 403、下载授权）。
///
/// 口径来源：第七轮 R7-CS1-01/02 建立的是「本机/内网/链路本地一律默认拒绝」，
/// 2026-10-04 由用户裁决改为「**本机与内网必须能打开**」——127.0.0.1、10/8、
/// 172.16/12、192.168/16、100.64/10（CGNAT/Tailscale）、::1、fc00::/7（ULA）
/// 以及 my-nas.local / printer.internal 这类主机名一律放行；本类只拦
/// **根本不是任何设备**的地址形态：
/// • 169.254.0.0/16 链路本地（含云厂商实例元数据端点 169.254.169.254）；
/// • 0.0.0.0/8 与 ::（未指定地址）、224.0.0.0/4 组播、255.255.255.255 广播、
///   240.0.0.0/4 保留；fe80::/10 与 ff00::/8；
/// • 文档与基准测试段：192.0.2.0/24、198.51.100.0/24、203.0.113.0/24、198.18.0.0/15。
///
/// 元数据端点为什么仍在拒绝名单：它不是"访问内网设备"，而是 SSRF 拿实例凭据的
/// 主路径（远程页面一张 <img> 就能读 user-data）。已知代价：阿里云元数据端点
/// 100.100.100.200 落在按裁决放行的 CGNAT 段内——记入残余，不假称已封。
///
/// 编码变体（八进制 0251.0376.0251.0376、十进制整数 2852168190、0x 十六进制、
/// 简写 169.254.1、前导零 0177.0.0.1）按「形态不规范即拒」处理，**不归一后再判**：
/// OS/Java 与 Chromium 对这些形态的 inet_aton 解释不同（CS-348/AD-213 记过），
/// 归一后再判就是让「按谁的解释」变成实现细节。此前本层正是先还原再判，于是
/// `0177.0.0.1`（=127.0.0.1）与 `169.1`（=169.0.0.1）被放行而 Android 拒它们——
/// 跨端契约向量 reserved-address-boundary.json 把这条分叉抓红（R9-B70 定稿）。
/// 非 IP 主机名一律放行：本机 hosts 与 mDNS 解析到内网属预期用法，DNS 才是这些名字的权威。</summary>
public static class ReservedAddressBoundary
{
    /// <summary>拒绝码单源（审计 reason 与 UI 文案都取此处，避免字符串分叉）。</summary>
    public const string DenyCode = "reserved_address";

    /// <summary>拒绝原因文案单源（与 DenyCode 同处定义，改口径只改这里）。</summary>
    public static DenyReason Reason { get; } = new DenyReason(
        DenyCode,
        "目标是链路本地/云元数据/组播/广播/保留或文档测试地址，不对应任何可访问设备，已按保留地址边界拒绝。");

    /// <summary>已解析地址是否落在保留地址边界内（true = 拒绝）。</summary>
    public static bool Denies(Uri? uri) => uri is not null && DeniesHost(uri.Host);

    /// <summary>裸地址形态（子资源与下载入口）。除解析后的 host 判定外，还查
    /// **原始 authority** 里的纯数字/0x 形态——.NET 的 Uri 会把它们归一成另一个
    /// 点分地址（实测 2852168190 → 170.0.161.254），而 Chromium 按 inet_aton 解析成
    /// 169.254.169.254（云元数据）；只看归一后的 host 就等于留一条绕过路。
    /// 解析不出绝对地址同样按拒绝处理：「无法判定即不得放行」。</summary>
    public static bool DeniesRaw(string? rawUrl) =>
        HasNumericAuthority(rawUrl)
        || (!Uri.TryCreate(rawUrl, UriKind.Absolute, out var uri) || Denies(uri));

    private static bool HasNumericAuthority(string? rawUrl)
    {
        if (string.IsNullOrEmpty(rawUrl))
            return false;
        var schemeEnd = rawUrl.IndexOf("://", StringComparison.Ordinal);
        if (schemeEnd < 0)
            return false;
        var rest = rawUrl[(schemeEnd + 3)..];
        var stop = rest.IndexOfAny('/', '?', '#');
        var authority = stop >= 0 ? rest[..stop] : rest;
        var at = authority.LastIndexOf('@');
        if (at >= 0)
            authority = authority[(at + 1)..];              // userinfo 不参与判定
        var colon = authority.LastIndexOf(':');
        if (colon > 0 && !authority.EndsWith(']'))
            authority = authority[..colon];                 // 剥端口（IPv6 带方括号，不动）
        // FQDN 的尾点是一个空标签，不是 inet_aton 变体：先剥掉再判形态，否则
        // `127.0.0.1.` 会被下面读成「五段不规范」而拒掉本机回环——正是 B8 裁决要求
        // 必须能打开的那一类（跨端向量条目 http://127.0.0.1./ 实测抓红，R9-B71）。
        authority = authority.TrimEnd('.');
        if (authority.Length == 0)
            return false;
        return authority.All(char.IsDigit)
            || (authority.StartsWith("0x", StringComparison.Ordinal)
                && authority.Length > 2
                && authority[2..].All(char.IsAsciiHexDigit))
            // ⑦ 也必须判在裸 authority 上：.NET 的 Uri 会先把 `169.1` 归一成
            // `169.0.0.1`、把 `0177.0.0.1` 归一成 `127.0.0.1`，只看归一后的 host 就等于
            // 让「按谁的 inet_aton 解释」决定放行与否（R9-B70，跨端契约向量抓红的那两条）。
            || IsNonCanonicalIpv4Authority(authority);
    }

    /// <summary>裸 authority 是否为「非规范的 IPv4 形态」（点分但段数≠4、前导零、空段、
    /// 0x 混写）。规范四段十进制不在这里判——它交解析后的段表。</summary>
    private static bool IsNonCanonicalIpv4Authority(string authority) =>
        HasNonCanonicalDottedForm(authority) && !IsCanonicalDottedIpv4(authority, out _);

    /// <summary>host 是否属"永不作为浏览目标"的保留地址形态。</summary>
    public static bool DeniesHost(string? host)
    {
        var normalized = (host ?? string.Empty).TrimEnd('.').ToLowerInvariant();
        if (normalized.Length == 0)
            return true;                                    // 无 host = 不可判定
        if (normalized.Length > 2 && normalized.StartsWith('[') && normalized.EndsWith(']'))
            normalized = normalized[1..^1];                 // IPv6 字面量的方括号
        if (normalized.Contains('%') || normalized.Contains('[') || normalized.Contains(']'))
            return true;                                    // zone-id/残留方括号：非设备地址
        // 纯数字/十六进制主机名（inet_aton 形态）一律拒绝：Chromium 按网络字节序
        // 归一（2852168190 → 169.254.169.254 元数据端点），而 .NET 的解析给的是
        // 另一串地址（实测 170.0.161.254）——两侧口径不同意味着"按 .NET 判定放行"
        // 就是留一条元数据绕过路；真实主机名不会是纯数字，误伤面为零。
        if (normalized.All(char.IsDigit) || normalized.StartsWith("0x", StringComparison.Ordinal))
            return true;
        // IPv6（含方括号形态）交解析器按字节判；带冒号却读不出来＝不可判定即拒。
        if (normalized.Contains(':'))
        {
            if (!IPAddress.TryParse(normalized, out var v6) || v6 is null)
                return true;
            return IsReserved(v6);
        }
        // ⑥ 规范点分十进制（正好 4 段、每段 1-3 位且无前导零）才进段表。
        if (IsCanonicalDottedIpv4(normalized, out var address))
            return IsReserved(address);
        // ⑦ 像 IPv4 却不规范（八进制 0177.0.0.1、简写 169.1、段数≠4、空段、0x 混写）一律拒：
        // OS/Java 与 Chromium 的 inet_aton 解释不同（CS-348/AD-213 记过），归一后再判就是把
        // 「按谁的解释」变成实现细节。此前本层走 UrlSafety 的归一化器，于是 0177.0.0.1
        //（=127.0.0.1）与 169.1（=169.0.0.1）被放行，而 Android 拒它们——跨端契约向量
        // reserved-address-boundary.json 把这条分叉抓红（R9-B70）。
        // ⑧ 其余是主机名 ⇒ 零 DNS，权威交 DNS（本机 hosts 与 mDNS 解析到内网属预期用法）。
        return HasNonCanonicalDottedForm(normalized);
    }

    /// <summary>规范点分十进制：正好 4 段、每段 1-3 位纯数字且无前导零（<c>0</c> 本身除外），
    /// 每段 ≤255。与 Android `AddressText.octetValueOrMinusOne`／`isDecimalOctet` 同一条判据。</summary>
    private static bool IsCanonicalDottedIpv4(string host, out IPAddress address)
    {
        address = default!;
        var parts = host.Split('.');
        if (parts.Length != 4)
            return false;
        var octets = new byte[4];
        for (var i = 0; i < 4; i++)
        {
            var part = parts[i];
            if (part.Length is < 1 or > 3 || !part.All(char.IsDigit) ||
                (part.Length > 1 && part[0] == '0'))
                return false;
            var value = int.Parse(part, CultureInfo.InvariantCulture);
            if (value > 255)
                return false;
            octets[i] = (byte)value;
        }
        address = new IPAddress(octets);
        return true;
    }

    /// <summary>点分但每段都是数字片段（纯数字、空段或 0x 前缀）＝按 inet_aton 解释的 IPv4
    /// 变体，不是主机名。与 Android `hasNumericAuthority` 同判据。</summary>
    private static bool HasNonCanonicalDottedForm(string host) =>
        host.Contains('.') &&
        host.Split('.').All(part => part.Length == 0 || part.All(char.IsDigit) ||
                                    part.StartsWith("0x", StringComparison.Ordinal));

    private static bool IsReserved(IPAddress address)
    {
        if (address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any))
            return true;                                        // 未指定地址
        if (address.IsIPv6LinkLocal || address.IsIPv6Multicast)
            return true;                                        // fe80::/10、ff00::/8
        var bytes = address.GetAddressBytes();
        if (bytes.Length == 16)
        {
            // 回环判定必须排在折叠之前（与核心 `security_policy/ipv6.rs`、Android
            // `LocalTargetHosts.isExemptIpv6` 同一条顺序）：`::1` 折出来是 `0.0.0.1`，
            // 而 0/8 在本表里是拒绝段——B8 裁决要求放行的本机回环会被自己人拦掉。
            if (IPAddress.IsLoopback(address))
                return false;
            // 内嵌 IPv4 的**两种**写法都要折：v4-mapped（`::ffff:x`，前置 80 位零 +
            // 第 11-12 字节 0xFF）与已废弃的 v4-compatible（`::x`，前置 96 位全零）。
            // 此前只折 v4-mapped，于是 `http://[::169.254.169.254]/` 穿过本边界——
            // 同一个云元数据端点，点分与 v4-mapped 写法被拒、这一写法被放行（R9-B69）。
            var mapped = bytes[..10].All(b => b == 0) && bytes[10] == 0xFF && bytes[11] == 0xFF;
            var compatible = bytes[..12].All(b => b == 0);
            if (mapped || compatible)
                return IsReserved(new IPAddress(bytes[12..]));
            // 6to4（2001::/32）与 Teredo（2001:20::/32）里内嵌的 IPv4 **不解码**：
            // Chromium 的 `net::IpAddress` 同样不解，解了三端会对同一地址给出不同裁决，
            // 多拦一层换来的是不一致。这是有意的口径选择，不是漏判。
            return false;
        }
        var b0 = bytes[0];
        if (b0 == 0)
            return true;                                        // 0.0.0.0/8
        if (b0 == 169 && bytes[1] == 254)
            return true;                                        // 链路本地 + 云元数据
        if (b0 == 192 && bytes[1] == 0 && bytes[2] == 2)
            return true;                                        // TEST-NET-1
        if (b0 == 198 && bytes[1] == 51 && bytes[2] == 100)
            return true;                                        // TEST-NET-2
        if (b0 == 203 && bytes[1] == 0 && bytes[2] == 113)
            return true;                                        // TEST-NET-3
        if (b0 == 198 && (bytes[1] == 18 || bytes[1] == 19))
            return true;                                        // 198.18.0.0/15 基准测试
        return b0 >= 224;                                       // 组播/保留/广播
    }
}

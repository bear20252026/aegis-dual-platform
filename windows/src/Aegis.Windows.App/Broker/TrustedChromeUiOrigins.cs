namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;

/// <summary>审计第七轮（2026-10-03）：受信 chrome UI 虚拟主机白名单——**单源**。
/// 这些主机不是网络地址：由宿主自己的 SetVirtualHostNameToFolderMapping 提供
/// （NtpAssets.BindVirtualHosts，AccessKind=Deny），映射目录仅发布输出内的
/// ntp/、geogebra/ 资源。此前「是否本地 UI 主机」的判定分散在
/// NtpAssets/WebView2Hardening/NtpBridge 三处常量与谓词（漂移面），本类收敛为
/// 唯一登记处；NtpAssets.HostName/GeoHostName 与 WebView2Hardening 均引用此处。
/// 用途边界（两级白名单，刻意不同宽严——见各方法注释）：
/// - 导航层私有/回环拒绝的豁免：IsLocalAssetDocument（ntp + geo，两者都是
///   宿主映射的本地资源页）；
/// - WebMessage 通道启用：仍只放行 NTP 桥唯一来源（NtpBridge.IsTrustedSource
///   ——仅 ntp，画板页无宿主桥，不得因为它「是本地的」就打开消息通道）。</summary>
public static class TrustedChromeUiOrigins
{
    /// <summary>新标签页虚拟主机名（NtpAssets.HostName 的规范源）。</summary>
    public const string NtpHost = "ntp.aegis.local";

    /// <summary>离线几何画板虚拟主机名（NtpAssets.GeoHostName 的规范源）。</summary>
    public const string GeoHost = "geo.aegis.local";

    private static readonly HashSet<string> Hosts = new(StringComparer.OrdinalIgnoreCase)
    {
        NtpHost, GeoHost,
    };

    /// <summary>host 是否为已登记的宿主自有虚拟主机（精确匹配——子域不放）。
    /// 按裸主机名比较并容忍尾点。</summary>
    public static bool IsTrustedVirtualHost(string? host) =>
        !string.IsNullOrWhiteSpace(host) && Hosts.Contains(host.TrimEnd('.'));

    /// <summary>是否为宿主自有本地资源文档地址（https + 默认端口 + 白名单虚拟主机）。
    /// 用于导航层私有/回环拒绝与 HTTPS-only 升级豁免——虚拟主机名以 .local 结尾，
    /// UrlSafety.IsPublicHost 判非公网，不豁免则首页/画板全被拒。</summary>
    public static bool IsLocalAssetDocument(Uri? uri) =>
        uri is not null
        && uri.Scheme == Uri.UriSchemeHttps
        && uri.IsDefaultPort
        && IsTrustedVirtualHost(uri.Host);
}

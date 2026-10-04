namespace Aegis.Windows.Broker;

using System;

/// <summary>审计第七轮（2026-10-04·R7-CS1-01/02）：隐私网络边界的**唯一谓词源**。
/// 同一条边界必须在四类出口成立——顶层导航（EvaluateNavigation）、授权消费
///（TryConsumeNavigation）、子资源（HostWebView.OnWebResourceRequested 返回 403）、
/// 下载（AllowDownload）。此前它只作用于导航：远程页面把目标改写成
/// &lt;img src="http://169.254.169.254/…"&gt;、fetch("http://192.168.1.1/…")
/// 或一个下载链接，就能带着用户 cookie 与内网位置触及本机服务、路由器配置口和
/// 云元数据端点，而「已拦远程页 SSRF/CSRF 原语」的声明只在顶层成立。
/// 三层判的是同一件事，故不得各写一份谓词（漂移面）。
///
/// 判定复用 UrlSafety.IsPublicHost 单源（覆盖 127.0.0.0/8、::1、0.0.0.0、
/// 169.254.0.0/16 含元数据 IP、10/8、172.16/12、192.168/16、fc00::/7、
/// CGNAT/组播/广播/保留段，以及十进制/十六进制/八进制/简写 IPv4 变体与
/// localhost/.local/.internal 主机名形态），不重解析第二套。
/// 唯一豁免：宿主自有虚拟主机（TrustedChromeUiOrigins——ntp/geo 本地资源页，
/// **不是**「所有 localhost」）。DNS 重bind（公网名解析到 127.0.0.1）属解析层
/// 问题：本层是纯语法判定，且 UI 线程同步 DNS 是 CS-339 已封的冻结面
///（跟进项见交付报告）。</summary>
public static class PrivateNetworkBoundary
{
    /// <summary>拒绝码单源——审计 reason 与 UI 文案都取此处，避免字符串分叉。</summary>
    public const string DenyCode = "private_network";

    /// <summary>拒绝原因文案单源（与 DenyCode 同处定义，改口径只改这里）。</summary>
    public static DenyReason Reason { get; } = new DenyReason(
        DenyCode, "目标为本机、内网或链路本地地址（含云元数据服务），已按隐私网络边界拒绝。");

    /// <summary>已解析地址是否落在隐私网络边界内（true = 默认拒绝）。</summary>
    public static bool Denies(Uri? uri) =>
        uri is not null
        && !TrustedChromeUiOrigins.IsLocalAssetDocument(uri)
        && !Core.UrlSafety.IsPublicHost(uri.Host);

    /// <summary>裸地址形态（下载入口）。解析不出绝对地址时按拒绝处理：本层语义是
    /// 「无法判定即不得放行」，空串/COM 抖动残留都落在这里。</summary>
    public static bool DeniesRaw(string? rawUrl) =>
        !Uri.TryCreate(rawUrl, UriKind.Absolute, out var uri) || Denies(uri);
}

namespace Aegis.Windows.WebView;

using System;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>HostWebView 的导航守卫分片（第八轮 B4 余量 R8-CS-SEC-02）：顶层导航的
/// 取消语义与「授权链求值异常 ⇒ 失败闭合」的判定核。从 HostWebView.cs 拆出是为了
/// 给新增的异常边界留出额度而不撑大行数基线（604 → 拆后回读同步收窄）。</summary>
public sealed partial class HostWebView
{
    /// <summary>导航决策（NavigationStarting 可 disallow——Microsoft 官方——真实取消语义）。</summary>
    private void OnNavigationStarting(CoreWebView2 webView, CoreWebView2NavigationStartingEventArgs e)
    {
        // HTTPS-only：http 主动升级为 https（Edge 同款——加密优先）。
        // 站点若无 https，升级后加载失败会走到错误页，绝不降级回明文。
        // 例外（豁免升级）：本机/回环/hosts 映射到本机的域名**不升级**——本地
        // 开发服务器通常只跑 http，升级到 https 必然失败（"开屏纯文字"根因）。
        // CS-382（2026-10-02 审计）：顶层路径本机判定同帧路径口径（CS-339）——
        // 此前冷缓存仍在 UI 线程同步 DNS（恶意页连开数个 hosts 域 http 链接即
        // 冻结 UI）；改只读缓存，未命中按非本机 fail-closed 升级 + 后台预热。
        // CS-388（2026-10-02 审计）：豁免扩展到非公网主机（内网/保留 IP 字面量
        // 及 .local/.internal 等内网域名后缀）——UrlNormalizer 对裸内网 IP
        //（如 192.168.1.1）补 http://，此前又被本升级路径改写 https 必失败
        //（两端口径互斥）；复用 UrlSafety.IsPublicHost 判定取反。
        // R8-CS-SEC-02（第八轮 2026-10-05）：取消先行——见 _onFrameNavigationStarting
        // 同款说明。TryAuthorizeNavigation 会经桥、事件订阅方（确认面板/拒绝提示）与
        // URL 解析，任何一处抛出都不该让顶层导航在未被授权的情况下放行。
        e.Cancel = true;
        if (_privacy.HttpsOnly
            && Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri)
            && uri.Scheme == Uri.UriSchemeHttp
            && !IsExemptFromHttpsUpgrade(uri.Host))
        {
            webView.Navigate(BuildHttpsUpgradeUrl(uri));
            return;
        }
        e.Cancel = !IsAuthorizedFailClosed(
            () => TryAuthorizeNavigation(
                webView, e.Uri, advancesDocumentGeneration: true), "顶层导航");
    }

    /// <summary>R8-CS-SEC-02：授权求值的失败闭合核——求值期异常按「未授权」处理。
    /// 提 internal 纯函数是因为 handler 本体要 COM 对象；没有它，这条判定面在无 COM
    /// 的常跑门禁里就无可断点（第八轮 §十一 队列项，本轮逐行回读后确证）。</summary>
    internal static bool IsAuthorizedFailClosed(Func<bool> authorize, string where)
    {
        try
        {
            return authorize();
        }
        catch (Exception ex)
        {
            SecurityLog.Write(
                $"[nav] {where}授权链求值异常——按失败闭合取消: {ex.GetType().Name}: {ex.Message}");
            return false;
        }
    }
}

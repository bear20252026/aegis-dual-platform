namespace Aegis.Host.WebView;

using System;
using Microsoft.Web.WebView2.Core;

/// <summary>WebView2 封装——全部安全事件入口经 broker（专家最终路线 + 全球调研：
/// NavigationStarting 可 disallow/WebResourceRequested 拦截/PermissionRequested 权限钩子）。
/// 远程页面无 native bridge——不注入任何 host object（XSS→RCE 风险消除）。</summary>
public sealed class HostWebView
{
    private readonly Broker.BrowserPolicyBroker _broker;
    private readonly string _sessionId;

    public HostWebView(Broker.BrowserPolicyBroker broker, string sessionId)
    {
        _broker = broker;
        _sessionId = sessionId;
    }

    public void WireEvents(CoreWebView2 webView)
    {
        // 导航决策（NavigationStarting 可 disallow——Microsoft 官方——真实取消语义）
        webView.NavigationStarting += (_, e) =>
        {
            var decision = _broker.EvaluateNavigation(_sessionId, "tab-0", 0, e.Uri, "navigation");
            if (decision is Broker.Decision.Deny)
                e.Cancel = true;  // 非允许导航真实取消（不再"仅日志"）
        };
        // 子框架导航同样经 broker（FrameNavigationStarting——iframe 策略）
        webView.FrameNavigationStarting += (_, e) =>
        {
            var decision = _broker.EvaluateNavigation(_sessionId, "tab-0", 0, e.Uri, "navigation");
            if (decision is Broker.Decision.Deny)
                e.Cancel = true;
        };
        // 消息只接受受信 chrome UI origin（远程页面无 native bridge——WebMessage 忽略）
        webView.WebMessageReceived += (_, e) =>
        {
            if (!IsTrustedChromeOrigin(e.Source))
                return;  // 远程消息忽略——无本地能力（后续接 broker ProposedAction）
        };
        // 每次新文档（ContentLoading）不注入任何 host object（远程页面零桥能力）
        // 权限请求（PermissionRequested）默认拒绝——最小授权（中文零信任实践）
        webView.PermissionRequested += (_, e) =>
        {
            e.State = CoreWebView2PermissionState.Deny;  // 远程页面无摄像头/麦克风/定位
        };
    }

    private static bool IsTrustedChromeOrigin(string source) =>
        source.StartsWith("file://", StringComparison.OrdinalIgnoreCase);
}

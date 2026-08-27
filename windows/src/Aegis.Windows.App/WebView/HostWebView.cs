namespace Aegis.Windows.WebView;

using System;
using Microsoft.Web.WebView2.Core;

/// <summary>WebView2 封装（阶段 C——蓝图 windows/src/Aegis.Windows.WebView）。
/// 只负责 WebView2 API 与事件转换——不拥有安全策略（ADR-002）。
/// 远程页面无 native bridge——不注入 host object（ADR-003）。</summary>
public sealed class HostWebView : IDisposable
{
    private readonly Broker.BrowserPolicyBroker _broker;
    private readonly string _sessionId;
    private readonly string _tabId;
    private ulong _documentGeneration;
    private bool _disposed;

    public HostWebView(Broker.BrowserPolicyBroker broker, string sessionId)
    {
        _broker = broker;
        _sessionId = sessionId;
        _tabId = $"tab-{sessionId}";
    }

    public void WireEvents(CoreWebView2 webView)
    {
        if (!_broker.RegisterSession(_sessionId, _tabId, _documentGeneration))
            throw new InvalidOperationException("无法注册安全浏览会话。");
        // 导航决策（NavigationStarting 可 disallow——Microsoft 官方——真实取消语义）
        webView.NavigationStarting += (_, e) =>
        {
            e.Cancel = !TryAuthorizeNavigation(e.Uri, advancesDocumentGeneration: true);
        };
        // 子框架导航同样经 broker（FrameNavigationStarting——iframe 策略）
        webView.FrameNavigationStarting += (_, e) =>
        {
            e.Cancel = !TryAuthorizeNavigation(e.Uri, advancesDocumentGeneration: false);
        };
        // 新窗口请求经 broker（NewWindowRequested——禁止绕过导航决策）
        webView.NewWindowRequested += (_, e) =>
        {
            // 没有已注册的受控子 WebView executor 时，禁止弹窗导航，避免策略被绕过。
            e.Handled = true;
        };
        // 消息只接受受信 chrome UI origin（远程页面无 native bridge——WebMessage 忽略）
        webView.WebMessageReceived += (_, e) =>
        {
            if (!IsTrustedChromeOrigin(e.Source))
                return;  // 远程消息忽略——无本地能力（后续接 broker ProposedAction）
        };
        // 权限请求（PermissionRequested）默认拒绝——最小授权（中文零信任实践）
        webView.PermissionRequested += (_, e) =>
        {
            e.State = CoreWebView2PermissionState.Deny;  // 远程页面无摄像头/麦克风/定位
        };
    }

    private static bool IsTrustedChromeOrigin(string source) =>
        Uri.TryCreate(source, UriKind.Absolute, out var uri)
        && uri.Scheme == Uri.UriSchemeHttps
        && uri.Host.Equals("chrome.aegis.local", StringComparison.OrdinalIgnoreCase)
        && uri.IsDefaultPort;

    public void Dispose()
    {
        if (_disposed)
            return;
        _broker.DestroySession(_sessionId);
        _disposed = true;
    }

    private bool TryAuthorizeNavigation(string rawUrl, bool advancesDocumentGeneration)
    {
        var decision = _broker.EvaluateNavigation(_sessionId, _tabId, _documentGeneration, rawUrl, "navigation");
        if (decision is not Broker.Decision.Allow allow
            || !_broker.TryConsumeNavigation(allow.Action, _sessionId, _tabId, _documentGeneration, rawUrl, "navigation"))
            return false;

        if (!advancesDocumentGeneration)
            return true;
        var nextGeneration = checked(_documentGeneration + 1);
        if (!_broker.UpdateDocumentGeneration(_sessionId, _tabId, nextGeneration))
            return false;
        _documentGeneration = nextGeneration;
        return true;
    }
}

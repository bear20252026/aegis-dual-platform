namespace Aegis.Windows.WebView;

using System;
using System.IO;
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
    private PendingNavigationConfirmation? _pendingConfirmation;
    private PendingNavigationResumption? _pendingResumption;
    private bool _disposed;

    /// <summary>仅受信 WPF chrome 订阅；远程页面无法调用此事件或取得授权动作。</summary>
    public event EventHandler<NavigationConfirmationRequestedEventArgs>? NavigationConfirmationRequested;

    /// <summary>待审批导航被批准、拒绝、替换或销毁时通知受信 chrome 关闭展示。</summary>
    public event EventHandler? NavigationConfirmationResolved;

    /// <summary>M3：危险扩展下载的用户确认请求（返回 true=允许下载）。
    /// 无订阅者时危险下载 fail-closed 拒绝。</summary>
    public event Func<string, string, bool>? DownloadConfirmationRequested;

    public HostWebView(Broker.BrowserPolicyBroker broker, string sessionId, string? tabId = null)
    {
        _broker = broker;
        _sessionId = sessionId;
        // M1-T1（ADR-009 多标签）：tabId 显式传入——每标签一个 HostWebView 实例
        //（每实例一个 broker session，账本键独立）。缺省保留旧单标签行为。
        _tabId = tabId ?? $"tab-{sessionId}";
    }

    public void WireEvents(CoreWebView2 webView)
    {
        if (!_broker.RegisterSession(_sessionId, _tabId, _documentGeneration))
            throw new InvalidOperationException("无法注册安全浏览会话。");
        // 导航决策（NavigationStarting 可 disallow——Microsoft 官方——真实取消语义）
        webView.NavigationStarting += (_, e) =>
        {
            e.Cancel = !TryAuthorizeNavigation(webView, e.Uri, advancesDocumentGeneration: true);
        };
        // 子框架导航同样经 broker（FrameNavigationStarting——iframe 策略）
        webView.FrameNavigationStarting += (_, e) =>
        {
            e.Cancel = !TryAuthorizeNavigation(webView, e.Uri, advancesDocumentGeneration: false);
        };
        // 新窗口请求经 broker（NewWindowRequested——禁止绕过导航决策）
        webView.NewWindowRequested += (_, e) =>
        {
            // 没有已注册的受控子 WebView executor 时，禁止弹窗导航，避免策略被绕过。
            e.Handled = true;
        };
        // M3 下载管理（ADR-009：pywebview 硬编码禁用下载的天花板在原生栈
        // 不复存在）。全量经 broker 审计；危险扩展（对齐 Android DownloadPolicy）
        // 需用户显式确认——无确认订阅者时 fail-closed 拒绝。
        webView.DownloadStarting += (_, e) =>
        {
            var downloadUrl = string.Empty;
            var suggested = string.Empty;
            try
            {
                downloadUrl = e.DownloadOperation?.Uri ?? string.Empty;
                // SDK 1.0.2903.40 无 SuggestedFileName——从结果路径提取
                suggested = Path.GetFileName(e.DownloadOperation?.ResultFilePath ?? string.Empty);
            }
            catch (Exception)
            {
                // 元数据读取失败不影响策略判定
            }
            var fileName = Core.Downloads.DownloadPolicy.SanitizeFileName(suggested);
            var dangerous = Core.Downloads.DownloadPolicy.RequiresExplicitConfirmation(downloadUrl, fileName);
            if (dangerous
                && (DownloadConfirmationRequested is null
                    || !DownloadConfirmationRequested.Invoke(downloadUrl, fileName)))
            {
                e.Handled = true;
                try
                {
                    e.DownloadOperation?.Cancel();
                }
                catch (Exception)
                {
                    // 操作可能尚未启动——拒绝语义已由 Handled 保证
                }
                _broker.DenyDownload(_sessionId, _tabId, downloadUrl);
                return;
            }
            _broker.AllowDownload(_sessionId, _tabId, downloadUrl, fileName, dangerous);
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
        // M1-T2（ADR-009）：加固束 + 原生红利接线
        WebView2Hardening.Apply(webView, _tabId);
        // 顶层/子框架导航时按来源翻转 WebMessage（远程页面禁用——fail-closed）
        webView.NavigationStarting += (_, e) => WebView2Hardening.SetPerOrigin(webView, e.Uri);
        webView.FrameNavigationStarting += (_, e) => WebView2Hardening.SetPerOrigin(webView, e.Uri);
        // DNT 注入 + 黑名单子资源真拦截（WebResourceRequested 原生返回 403——
        // pywebview 时代只能标记不能拦截的缺口，原生 API 直接闭合）
        webView.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
        webView.WebResourceRequested += (_, e) =>
        {
            try
            {
                e.Request.Headers.SetHeader("DNT", "1");
                if (Uri.TryCreate(e.Request.Uri, UriKind.Absolute, out var uri)
                    && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps)
                    && _broker.IsHostBlocked(uri.Host))
                {
                    Core.Security.SecurityLog.Write(
                        $"[threat] 子资源拦截（黑名单命中）: {e.Request.Uri}");
                    e.Response = webView.Environment.CreateWebResourceResponse(
                        null, 403, "Blocked", "Content-Type: text/plain");
                }
            }
            catch (Exception)
            {
                // 单请求处理失败不影响其他请求（保持原始响应路径）
            }
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
        RejectPendingNavigation();
        _broker.DestroySession(_sessionId);
        _disposed = true;
    }

    /// <summary>
    /// 由受信 chrome 的明确按钮调用。批准入口不会自建动作；它仅以核心登记的 nonce
    /// 兑换原始授权，然后经下一次 NavigationStarting 完成唯一一次 consume。
    /// </summary>
    public bool ApprovePendingNavigation(CoreWebView2 webView)
    {
        if (_pendingConfirmation is not { } pending || _disposed)
            return false;
        _pendingConfirmation = null;
        var decision = _broker.ApproveNavigationConfirmation(pending.Request, pending.RawUrl, pending.Scope);
        if (decision is not Broker.Decision.Allow allow)
        {
            NavigationConfirmationResolved?.Invoke(this, EventArgs.Empty);
            return false;
        }
        _pendingResumption = new PendingNavigationResumption(pending.RawUrl, pending.Scope, allow.Action);
        NavigationConfirmationResolved?.Invoke(this, EventArgs.Empty);
        webView.Navigate(pending.RawUrl);
        return true;
    }

    /// <summary>由拒绝按钮、对话框关闭、会话销毁或新请求替换时调用；失败也不得恢复导航。</summary>
    public bool RejectPendingNavigation()
    {
        if (_pendingConfirmation is not { } pending)
            return false;
        _pendingConfirmation = null;
        _pendingResumption = null;
        var rejected = _broker.RejectNavigationConfirmation(pending.Request);
        NavigationConfirmationResolved?.Invoke(this, EventArgs.Empty);
        return rejected;
    }

    private bool TryAuthorizeNavigation(CoreWebView2 webView, string rawUrl, bool advancesDocumentGeneration)
    {
        if (advancesDocumentGeneration && TryResumeApprovedNavigation(rawUrl))
            return AdvanceDocumentGenerationIfNeeded();

        if (advancesDocumentGeneration && NavigationConfirmationGate.IsRequired)
        {
            if (_pendingConfirmation is not null)
            {
                // 新的顶层请求使旧请求失效，但不自动替换或自动批准，避免 UI 与 URL 脱钩。
                RejectPendingNavigation();
                return false;
            }
            var confirmationDecision = _broker.RequestNavigationConfirmation(
                _sessionId, _tabId, _documentGeneration, rawUrl, "navigation");
            if (confirmationDecision is Broker.Decision.RequireConfirmation confirmation)
            {
                _pendingConfirmation = new PendingNavigationConfirmation(rawUrl, "navigation", confirmation.Request);
                NavigationConfirmationRequested?.Invoke(
                    this,
                    new NavigationConfirmationRequestedEventArgs(confirmation.Request));
                return false;
            }
            // 原生核心、会话或协议错误均不能继续；若未来策略直接 Allow，仍走既有消费边界。
            if (confirmationDecision is not Broker.Decision.Allow immediate
                || !_broker.TryConsumeNavigation(immediate.Action, _sessionId, _tabId, _documentGeneration, rawUrl, "navigation"))
                return false;
            return AdvanceDocumentGenerationIfNeeded();
        }

        var decision = _broker.EvaluateNavigation(_sessionId, _tabId, _documentGeneration, rawUrl, "navigation");
        if (decision is not Broker.Decision.Allow allow
            || !_broker.TryConsumeNavigation(allow.Action, _sessionId, _tabId, _documentGeneration, rawUrl, "navigation"))
            return false;

        if (!advancesDocumentGeneration)
            return true;
        return AdvanceDocumentGenerationIfNeeded();
    }

    private bool TryResumeApprovedNavigation(string rawUrl)
    {
        if (_pendingResumption is not { } pending)
            return false;
        // 批准只允许恢复紧随其后的同一 URL。任何 URL 变化都放弃宿主持有的已批准动作，
        // 不能让后续请求借用过期的恢复状态；核心账本中的不可达动作仍会按自身过期规则失效。
        if (!string.Equals(pending.RawUrl, rawUrl, StringComparison.Ordinal))
        {
            _pendingResumption = null;
            return false;
        }
        _pendingResumption = null;
        return _broker.TryConsumeNavigation(
            pending.Action,
            _sessionId,
            _tabId,
            _documentGeneration,
            rawUrl,
            pending.Scope);
    }

    private bool AdvanceDocumentGenerationIfNeeded()
    {
        var nextGeneration = checked(_documentGeneration + 1);
        if (!_broker.UpdateDocumentGeneration(_sessionId, _tabId, nextGeneration))
            return false;
        _documentGeneration = nextGeneration;
        return true;
    }

    private sealed record PendingNavigationConfirmation(
        string RawUrl,
        string Scope,
        Broker.ApprovalRequest Request);

    private sealed record PendingNavigationResumption(
        string RawUrl,
        string Scope,
        Broker.AuthorizedAction Action);
}

/// <summary>交给受信 WPF chrome 的最小确认展示数据；不含可消费授权或远程网页内容。</summary>
public sealed class NavigationConfirmationRequestedEventArgs : EventArgs
{
    public NavigationConfirmationRequestedEventArgs(Broker.ApprovalRequest request) => Request = request;

    public Broker.ApprovalRequest Request { get; }
}

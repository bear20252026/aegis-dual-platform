namespace Aegis.Windows.WebView;

using System;
using System.IO;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Privacy;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>WebView2 封装（阶段 C——蓝图 windows/src/Aegis.Windows.WebView）。
/// 只负责 WebView2 API 与事件转换——不拥有安全策略（ADR-002）。
/// 远程页面无 native bridge——不注入 host object（ADR-003）。</summary>
public sealed class HostWebView : IDisposable
{
    private readonly IBroker _broker;
    private readonly IPrivacySettings _privacy;
    private readonly string _sessionId;
    private readonly string _tabId;
    private ulong _documentGeneration;
    private PendingNavigationConfirmation? _pendingConfirmation;
    private PendingNavigationResumption? _pendingResumption;
    private bool _disposed;

    // —— 命名处理器（审计遗留项：此前匿名闭包订阅不可退订，且重复 Wire 会
    //    双重订阅导致每导航双重决策/双重消费）——
    private CoreWebView2? _wired;
    private EventHandler<CoreWebView2NavigationStartingEventArgs>? _onNavigationStarting;
    private EventHandler<CoreWebView2NavigationStartingEventArgs>? _onNavigationOriginFlip;
    private EventHandler<CoreWebView2NavigationStartingEventArgs>? _onFrameNavigationStarting;
    private EventHandler<CoreWebView2NewWindowRequestedEventArgs>? _onNewWindowRequested;
    private EventHandler<CoreWebView2DownloadStartingEventArgs>? _onDownloadStarting;
    private EventHandler<CoreWebView2PermissionRequestedEventArgs>? _onPermissionRequested;
    private EventHandler<CoreWebView2WebResourceRequestedEventArgs>? _onWebResourceRequested;

    /// <summary>仅受信 WPF chrome 订阅；远程页面无法调用此事件或取得授权动作。</summary>
    public event EventHandler<NavigationConfirmationRequestedEventArgs>? NavigationConfirmationRequested;

    /// <summary>待审批导航被批准、拒绝、替换或销毁时通知受信 chrome 关闭展示。</summary>
    public event EventHandler? NavigationConfirmationResolved;

    /// <summary>M3：危险扩展下载的用户确认请求（返回 true=允许下载）。
    /// 无订阅者时危险下载 fail-closed 拒绝。</summary>
    public event Func<string, string, bool>? DownloadConfirmationRequested;

    /// <summary>新窗口请求（target=_blank / window.open 等）。宿主拦截原生弹窗，
    /// 把 URL 交给受信 chrome 在新标签页打开——链接点击不再失效（此前一律
    /// Handled=true 静默丢弃 → 新闻/热搜等 target=_blank 链接点击无反应）。</summary>
    public event Action<string>? NewWindowRequested;

    /// <summary>CS-355（2026-10-01 审计）：策略拒绝导航的原因上抛受信 chrome。
    /// 此前 broker 的 DenyReason 被 TryAuthorizeNavigation 丢弃（只回 false），
    /// 取消导航的 NavigationCompleted 以 OperationCanceled 呈现——零可见反馈。
    /// 参数为用户可读的拒绝说明（DenyReason.Detail）。</summary>
    public event Action<string>? NavigationDenied;

    /// <summary>构造器注入授权边界与隐私策略读取面（默认 LivePrivacySettings——
    /// 读进程级静态；测试可注入假实现）。</summary>
    public HostWebView(IBroker broker, string sessionId, string? tabId = null, IPrivacySettings? privacy = null)
    {
        _broker = broker ?? throw new ArgumentNullException(nameof(broker));
        _privacy = privacy ?? LivePrivacySettings.Instance;
        _sessionId = sessionId;
        // M1-T1（ADR-009 多标签）：tabId 显式传入——每标签一个 HostWebView 实例
        //（每实例一个 broker session，账本键独立）。缺省保留旧单标签行为。
        _tabId = tabId ?? $"tab-{sessionId}";
    }

    /// <summary>接线（幂等防护：同一 WebView 只允许接线一次——重复接线会双重
    /// 订阅导致每导航双重决策/双重消费，直接拒绝）。</summary>
    public void WireEvents(CoreWebView2 webView)
    {
        if (_wired is not null)
            throw new InvalidOperationException("HostWebView 已接线（重复 Wire 禁止）。");
        if (!_broker.RegisterSession(_sessionId, _tabId, _documentGeneration))
            throw new InvalidOperationException("无法注册安全浏览会话。");
        _wired = webView;

        _onNavigationStarting = (sender, e) => OnNavigationStarting(webView, e);
        // CS-317（2026-09-26 审计）：HTTPS-only 对 iframe 子文档同判——顶层
        // http 会升级 https 而 http frame 保持明文是策略缺口。帧无法重定向
        // 顶层导航，只能取消并留审计（本机/回环例外口径与顶层一致）。
        // CS-339（2026-10-01 审计）：帧路径本机判定改只读缓存——此前
        // IsLocalHostOrResolvesLocalHost 缓存未命中即在 UI 线程同步 DNS，
        // 恶意页嵌多个不可解析 http iframe 即逐帧冻结 UI；未命中 fail-closed
        // 取消 + 后台预热（下次加载命中缓存即恢复 hosts 本地域名放行）。
        _onFrameNavigationStarting = (sender, e) =>
        {
            if (_privacy.HttpsOnly
                && Uri.TryCreate(e.Uri, UriKind.Absolute, out var frameUri)
                && frameUri.Scheme == Uri.UriSchemeHttp
                && !TryClassifyFrameHostAsLocal(frameUri.Host))
            {
                e.Cancel = true;
                SecurityLog.Write($"[https] 明文 iframe 导航已取消: {RedactUrl(e.Uri)}");
                return;
            }
            e.Cancel = !TryAuthorizeNavigation(webView, e.Uri, advancesDocumentGeneration: false);
        };
        _onNewWindowRequested = (sender, e) =>
        {
            e.Handled = true;  // 一律不弹独立窗口
            if (!string.IsNullOrWhiteSpace(e.Uri))
                NewWindowRequested?.Invoke(e.Uri);
        };
        _onDownloadStarting = (sender, e) => OnDownloadStarting(e);
        _onPermissionRequested = (sender, e) =>
            e.State = CoreWebView2PermissionState.Deny;  // 远程页面无摄像头/麦克风/定位
        // 顶层导航时按来源翻转 WebMessage（远程页面禁用——fail-closed）。
        // 注意：只按顶层 NavigationStarting 翻转，**绝不因内嵌 iframe 的
        // 来源启用**（IsWebMessageEnabled 是 core 级全局开关——若子框架为
        // ntp.aegis.local 就把全局打开，远程页可内嵌该帧驱动受信桥——
        // 审计 M4 发现并封死）。
        _onNavigationOriginFlip = (sender, e) => WebView2Hardening.SetPerOrigin(webView, e.Uri);
        _onWebResourceRequested = (sender, e) => OnWebResourceRequested(webView, e);

        webView.NavigationStarting += _onNavigationStarting;
        webView.FrameNavigationStarting += _onFrameNavigationStarting;
        webView.NewWindowRequested += _onNewWindowRequested;
        webView.DownloadStarting += _onDownloadStarting;
        webView.PermissionRequested += _onPermissionRequested;
        webView.NavigationStarting += _onNavigationOriginFlip;
        webView.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
        webView.WebResourceRequested += _onWebResourceRequested;
        // M1-T2（ADR-009）：加固束 + 原生红利接线
        WebView2Hardening.Apply(webView, _tabId);
    }

    /// <summary>显式解绑全部订阅（Dispose 调用；也可供宿主在复用 WebView 时手动
    /// 退订——此前匿名闭包不可退订，阻止单测复用同一 WebView 实例）。</summary>
    public void UnwireEvents()
    {
        if (_wired is not { } webView)
            return;
        webView.NavigationStarting -= _onNavigationStarting;
        webView.NavigationStarting -= _onNavigationOriginFlip;
        webView.FrameNavigationStarting -= _onFrameNavigationStarting;
        webView.NewWindowRequested -= _onNewWindowRequested;
        webView.DownloadStarting -= _onDownloadStarting;
        webView.PermissionRequested -= _onPermissionRequested;
        webView.WebResourceRequested -= _onWebResourceRequested;
        _wired = null;
    }

    /// <summary>导航决策（NavigationStarting 可 disallow——Microsoft 官方——真实取消语义）。</summary>
    private void OnNavigationStarting(CoreWebView2 webView, CoreWebView2NavigationStartingEventArgs e)
    {
        // HTTPS-only：http 主动升级为 https（Edge 同款——加密优先）。
        // 站点若无 https，升级后加载失败会走到错误页，绝不降级回明文。
        // 例外：本机/回环/hosts 映射到本机的域名**不升级**——本地开发
        // 服务器通常只跑 http，升级到 https 必然失败（"开屏纯文字"根因）。
        if (_privacy.HttpsOnly
            && Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri)
            && uri.Scheme == Uri.UriSchemeHttp
            && !Core.UrlSafety.IsLocalHostOrResolvesLocalHost(uri.Host))
        {
            e.Cancel = true;
            webView.Navigate(BuildHttpsUpgradeUrl(uri));
            return;
        }
        e.Cancel = !TryAuthorizeNavigation(webView, e.Uri, advancesDocumentGeneration: true);
    }

    /// <summary>CS-362（2026-10-01 审计）：HTTPS-only 升级 URL 构造提纯 internal
    /// 直测。实验（.NET 10）：UriComponents.HostAndPort 会**补默认端口**
    /// （http://example.com → "example.com:80"）——原内联实现产出
    /// https://example.com:80/…（https 走 80 端口的隐性升级断裂），改用
    /// Uri.Authority（不含 userinfo/默认端口、IPv6 保留方括号）+ PathAndQuery。</summary>
    internal static string BuildHttpsUpgradeUrl(Uri uri) =>
        "https://" + uri.Authority
        + uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped);

    /// <summary>CS-339（2026-10-01 审计）：帧路径本机判定——只读缓存探测，
    /// 绝不在 UI 线程同步 DNS。命中（显式本机名/回环 IP/既有缓存）按判定
    /// 返回；未命中 fail-closed 视为非本机（本次帧导航取消），并后台预热
    /// 缓存（下一次加载命中即恢复放行语义——hosts 本地域名开发场景）。</summary>
    private static bool TryClassifyFrameHostAsLocal(string host)
    {
        if (Core.UrlSafety.TryGetCachedLocalHost(host, out var isLocal))
            return isLocal;
        var captured = host;
        _ = System.Threading.Tasks.Task.Run(
            () => Core.UrlSafety.IsLocalHostOrResolvesLocalHost(captured));
        return false;
    }

    /// <summary>M3 下载管理（ADR-009）：全量经 broker 审计；危险扩展（对齐
    /// Android DownloadPolicy）需用户显式确认——无确认订阅者时 fail-closed 拒绝。</summary>
    private void OnDownloadStarting(CoreWebView2DownloadStartingEventArgs e)
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
        // 下载门禁真正生效：AllowDownload 校验会话/标签/kill-switch，
        // 返回值接入实际放行——此前被忽略（ADR-002 审计发现 G）。
        // 非危险下载或危险已确认，都必须过这道门。
        var allowed = _broker.AllowDownload(_sessionId, _tabId, downloadUrl, fileName, dangerous);
        if (!allowed)
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
        }
    }

    /// <summary>DNT 注入 + 黑名单子资源真拦截（WebResourceRequested 原生返回
    /// 403——pywebview 时代只能标记不能拦截的缺口，原生 API 直接闭合）。</summary>
    private void OnWebResourceRequested(CoreWebView2 webView, CoreWebView2WebResourceRequestedEventArgs e)
    {
        try
        {
            e.Request.Headers.SetHeader("DNT", "1");
            if (!Uri.TryCreate(e.Request.Uri, UriKind.Absolute, out var uri)
                || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
                return;
            // 威胁黑名单（既有——子资源真拦截）
            if (_broker.IsHostBlocked(uri.Host))
            {
                Core.Security.SecurityLog.Write(
                    $"[threat] 子资源拦截（黑名单命中）: {RedactUrl(e.Request.Uri)}");
                e.Response = webView.Environment.CreateWebResourceResponse(
                    null, 403, "Blocked", "Content-Type: text/plain");
                return;
            }
            // 跟踪防护分级（P1——对齐 Edge 基础/均衡/严格）
            var level = _privacy.ProtectionLevel;
            if (level <= 0)
                return;
            var pageHost = ResolvePageHost(webView.Source);
            // 受信虚拟主机（NTP/GeoGebra）子资源：黑名单仍拦截（上文已处理），
            // 但跳过第三方/跟踪判定——严格模式 + 跨站导航过渡期会把自带页的
            // JS/WASM 误判为第三方而 403（pageHost 仍是旧的远程 host）。
            var isVirtualHostAsset = NtpAssets.IsVirtualHostUrl(e.Request.Uri);
            var isTracker = Core.Privacy.TrackerList.IsTracker(uri.Host);
            var blockContext = e.ResourceContext is CoreWebView2WebResourceContext.Script
                or CoreWebView2WebResourceContext.Fetch
                or CoreWebView2WebResourceContext.Image;
            if (isTracker
                || (level >= 2 && blockContext && !isVirtualHostAsset
                    && !Core.Privacy.TrackerList.IsSameSite(uri.Host, pageHost)))
            {
                RecordTrackerBlock(uri, level, e.ResourceContext);
                e.Response = webView.Environment.CreateWebResourceResponse(
                    null, 403, "Blocked", "Content-Type: text/plain");
            }
        }
        catch (Exception ex)
        {
            // CS-310（2026-09-26 审计）：兜底不再完全静默——策略管线异常留痕
            //（含 ResourceContext 与脱敏 URL），维持不 rethrow（单请求处理
            // 失败不影响其他请求，保持原始响应路径）
            try
            {
                SecurityLog.Write(
                    $"[webresource] 处理异常: {ex.GetType().Name}: {ex.Message} ctx={e.ResourceContext} url={RedactUrl(e.Request.Uri)}");
            }
            catch (Exception)
            {
                // 异常参数本身不可读——尽力留痕即止
            }
        }
    }

    // —— CS-308（2026-09-26 审计）：拦截类事件聚合落盘 ——
    // 跟踪器密集页此前每个被拦截子请求同步 SecurityLog.Write（每条
    // File.AppendAllText）——IO 放大且 1MB 取证日志被冲掉。按 host 聚合计数，
    // 周期性（累计 BlockAggregateFlushThreshold 次）落一行；Dispose 兜底清空。
    // CS-363（2026-10-01 审计）：聚合逻辑提纯到 TrackerBlockAggregator
    //（单测直测聚合/阈值/尾部 flush），HostWebView 只保留落盘接线。
    private readonly TrackerBlockAggregator _trackerBlocks = new(BlockAggregateFlushThreshold);

    private const int BlockAggregateFlushThreshold = TrackerBlockAggregator.DefaultFlushThreshold;

    private void RecordTrackerBlock(Uri uri, int level, CoreWebView2WebResourceContext context)
    {
        if (_trackerBlocks.Record(uri.Host, $"级别{level} ctx={context}"))
            FlushTrackerBlocks();
    }

    private void FlushTrackerBlocks()
    {
        foreach (var row in _trackerBlocks.Drain())
        {
            SecurityLog.Write(
                $"[privacy] 跟踪防护拦截聚合: {row.Host} ×{row.Count}（{row.Detail}）");
        }
    }

    // CS-070（审计 2026-09-25）：脱敏单源——与 Broker 各持一份相同实现已收敛
    // 到 UrlRedactor.Redact（丢弃 query/fragment，超长截断）。
    private static string RedactUrl(string? url) => UrlRedactor.Redact(url);


    public void Dispose()
    {
        if (_disposed)
            return;
        UnwireEvents();
        RejectPendingNavigation();
        // CS-308：会话结束时落最后一批未满阈值的拦截聚合（取证不留尾巴）
        if (_trackerBlocks.PendingCount > 0)
            FlushTrackerBlocks();
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
            if (confirmationDecision is Broker.Decision.Deny confirmationDeny)
            {
                // CS-355：确认门前的直接拒绝同样上抛原因（不只静默取消）
                NavigationDenied?.Invoke(confirmationDeny.Reason.Detail);
                return false;
            }
            if (confirmationDecision is not Broker.Decision.Allow immediate
                || !_broker.TryConsumeNavigation(immediate.Action, _sessionId, _tabId, _documentGeneration, rawUrl, "navigation"))
                return false;
            return AdvanceDocumentGenerationIfNeeded();
        }

        var decision = _broker.EvaluateNavigation(_sessionId, _tabId, _documentGeneration, rawUrl, "navigation");
        if (decision is Broker.Decision.Deny deny)
        {
            // CS-355（2026-10-01 审计）：拒绝原因上抛受信 chrome——此前被
            // OperationCanceled 过滤，用户只看到"导航无反应"
            NavigationDenied?.Invoke(deny.Reason.Detail);
            return false;
        }
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

    // CS-198：pageHost 解析缓存——每个子资源请求都重 Parse webView.Source
    // （同页上百子资源重复解析）；来源串不变即复用，导航换页即失效
    private string? _pageHostCacheSource;
    private string _pageHostCacheValue = string.Empty;

    private string ResolvePageHost(string? source)
    {
        if (!string.Equals(_pageHostCacheSource, source, StringComparison.Ordinal))
        {
            _pageHostCacheSource = source;
            _pageHostCacheValue = Uri.TryCreate(source, UriKind.Absolute, out var page)
                ? page.Host
                : string.Empty;
        }
        return _pageHostCacheValue;
    }

    private bool AdvanceDocumentGenerationIfNeeded()
    {
        // CS-199：代际饱和前置守卫——checked 溢出异常发生在导航事件链上
        // 即崩溃面；int 代际实际不可达，守卫为契约兜底（饱和按推进失败
        // fail-closed 拒绝）
        if (_documentGeneration == int.MaxValue)
            return false;
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

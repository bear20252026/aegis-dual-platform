namespace Aegis.Windows.WebView;

using System;
using System.Collections.Generic;
using System.IO;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Privacy;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>WebView2 封装（阶段 C——蓝图 windows/src/Aegis.Windows.WebView）。
/// 只负责 WebView2 API 与事件转换——不拥有安全策略（ADR-002）。
/// 远程页面无 native bridge——不注入 host object（ADR-003）。
/// 分片：拦截事件落盘接线见 HostWebView.TrackerBlocks.cs，
/// 导航守卫见 HostWebView.NavigationGuards.cs，子资源守卫见 HostWebView.WebResourceGuards.cs。</summary>
public sealed partial class HostWebView : IDisposable
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

    /// <summary>审计第六轮（2026-10-03）：安全事件是否已完成接线。宿主导航入口
    /// 须以此 fail-closed——未接线的控件被设置 Source 时会隐式初始化成默认
    /// 环境（零策略处理器），等于旁路整个 ADR-002 授权面。</summary>
    public bool IsWired => _wired is not null;
    private EventHandler<CoreWebView2NavigationStartingEventArgs>? _onNavigationStarting;
    private EventHandler<CoreWebView2NavigationStartingEventArgs>? _onNavigationOriginFlip;
    private EventHandler<CoreWebView2NavigationStartingEventArgs>? _onFrameNavigationStarting;
    private EventHandler<CoreWebView2NewWindowRequestedEventArgs>? _onNewWindowRequested;
    private EventHandler<CoreWebView2DownloadStartingEventArgs>? _onDownloadStarting;
    private EventHandler<CoreWebView2PermissionRequestedEventArgs>? _onPermissionRequested;
    private EventHandler<CoreWebView2WebResourceRequestedEventArgs>? _onWebResourceRequested;

    // 审计第六轮（2026-10-03）：紧急终止的**进程级反应**接线。此前
    // KillSwitch.RegisterProcessReaction 建好却零调用者——Engage 只冻结
    // broker 入口判定，已建立的内核仍继续流式拉取 XHR/子资源、进行中的
    // 下载照常完成，与"进程级紧急冻结"承诺不符。本实例接线期间登记反应，
    // 解绑时注销（开关不得持有已释放控件）。
    private IDisposable? _killSwitchReaction;
    private readonly object _downloadsLock = new();
    private readonly List<CoreWebView2DownloadOperation> _trackedDownloads = new();

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

    /// <summary>接线（幂等防护：同一 WebView 只允许接线一次——重复接线会双重订阅导致
    /// 每导航双重决策/双重消费）。R8-CS-SEC-11：`_wired` 只在本方法**末尾**置位。</summary>
    public void WireEvents(CoreWebView2 webView)
    {
        if (_wired is not null)
            throw new InvalidOperationException("HostWebView 已接线（重复 Wire 禁止）。");
        if (!_broker.RegisterSession(_sessionId, _tabId, _documentGeneration))
            throw new InvalidOperationException("无法注册安全浏览会话。");

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
            // R8-CS-SEC-02（第八轮 2026-10-05）：取消先行。原写法末句
            // e.Cancel = !TryAuthorizeNavigation(...) 在求值期抛出时整句作废，
            // e.Cancel 停在默认 false —— 子帧照常加载，即 fail-open；条件求值本身
            // （Uri 解析/本机判定）也一样能抛。现先落 fail-closed 默认，判定通过才放行。
            e.Cancel = true;
            try
            {
                if (_privacy.HttpsOnly
                    && Uri.TryCreate(e.Uri, UriKind.Absolute, out var frameUri)
                    && frameUri.Scheme == Uri.UriSchemeHttp
                    && !TryClassifyFrameHostAsLocal(frameUri.Host))
                {
                    SecurityLog.Write($"[https] 明文 iframe 导航已取消: {RedactUrl(e.Uri)}");
                    return;
                }
                e.Cancel = !IsAuthorizedFailClosed(
                    () => TryAuthorizeNavigation(
                        webView, e.Uri, advancesDocumentGeneration: false), "子帧");
            }
            catch (Exception ex)
            {
                SecurityLog.Write(
                    $"[nav] 子帧策略链外层异常——维持取消: {ex.GetType().Name}: {ex.Message}");
                e.Cancel = true;
            }
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
        // 审计第六轮（2026-10-03）：本处理器订阅在取消处理器**之后**，故
        // broker 已 Cancel 的导航仍会执行翻转——按未经提交的 URL 改通道状态。
        // 目标为受信 host 而导航被取消时，屏幕显示的仍是旧远程文档，通道却被
        // 打开。加 e.Cancel 短路：被取消的导航不改状态（显示文档未变）。
        _onNavigationOriginFlip = (sender, e) =>
        {
            if (e.Cancel)
                return;
            WebView2Hardening.SetPerOrigin(webView, e.Uri);
        };
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
        // 审计第六轮（2026-10-03）：登记紧急终止反应。已处于终止态时
        // RegisterProcessReaction 立即执行（新建标签同样被冻结——fail-closed）。
        // Engage 与本接线同在 UI 线程（WPF），CoreWebView2.Stop 的线程要求满足。
        _killSwitchReaction = _broker.KillSwitch.RegisterProcessReaction(StopLiveTraffic);
        _wired = webView;
    }

    /// <summary>审计第六轮（2026-10-03）：紧急终止的进程级反应——中止本 WebView
    /// 的在途流量。broker 入口的 IsEngaged 判定只能挡住**新的**副作用请求；
    /// 已建立的流式子资源与进行中的下载不会自行停下，故必须显式 Stop/Cancel，
    /// 否则"冻结全进程"名不副实。</summary>
    private void StopLiveTraffic()
    {
        try
        {
            _wired?.Stop();
        }
        catch (Exception)
        {
            // 内核可能已销毁——终止语义已由入口判定保证，不放大异常
            SecurityLog.Write($"[killswitch] tab={_tabId} 内核 Stop 未生效（可能已销毁）");
        }
        CoreWebView2DownloadOperation[] snapshot;
        lock (_downloadsLock)
            snapshot = _trackedDownloads.ToArray();
        foreach (var download in snapshot)
        {
            try
            {
                download.Cancel();
            }
            catch (Exception)
            {
                // 下载可能已完成——取消失败不改变拒绝语义
            }
        }
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
        // 审计第六轮（2026-10-03）：注销紧急终止反应并丢在途下载引用——
        // 开关的注册表若继续持有已释放控件，Engage 时即对死对象调 Stop/Cancel
        _killSwitchReaction?.Dispose();
        _killSwitchReaction = null;
        lock (_downloadsLock)
            _trackedDownloads.Clear();
        _wired = null;
    }

    /// <summary>CS-382/388：HTTPS-only 升级豁免判定（纯同步——绝不在 UI 线程
    /// 发起 DNS）。非公网主机直接豁免；本机/hosts 域走只读缓存，未命中按
    /// 非本机处理（本次升级 https）并后台预热缓存（下次加载命中即恢复放行）。
    /// 提 internal 供直测。</summary>
    internal static bool IsExemptFromHttpsUpgrade(string host)
    {
        if (!Core.UrlSafety.IsPublicHost(host))
            return true;  // 内网/保留 IP 字面量与内网域名——本地服务通常只跑 http
        if (Core.UrlSafety.TryGetCachedLocalHost(host, out var isLocal))
            return isLocal;
        var captured = host;
        _ = System.Threading.Tasks.Task.Run(
            () => Core.UrlSafety.IsLocalHostOrResolvesLocalHost(captured));
        return false;  // 未命中 fail-closed 视为非本机（升级 https）
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
        var metadataReadable = true;
        try
        {
            downloadUrl = e.DownloadOperation?.Uri ?? string.Empty;
            // SDK 1.0.2903.40 无 SuggestedFileName——从结果路径提取
            suggested = Path.GetFileName(e.DownloadOperation?.ResultFilePath ?? string.Empty);
        }
        catch (Exception)
        {
            metadataReadable = false;
        }
        // 审计第六轮（2026-10-03）：元数据**就是**策略输入，不是可忽略的旁路。
        // 此前读取失败被吞成空串——SanitizeFileName("") 得 benign 默认名、
        // RequiresExplicitConfirmation("","aegis_download") 判非危险、
        // AllowDownload(session,tab,"",…) 因会话仍在而返回 true，于是 COM 抖动
        // 一次就让 Content-Disposition: evil.exe 静默落盘（fail-open）。
        // 现口径：读不到 / 无 URL / 无操作对象 = 按危险处理，无确认订阅者即拒。
        if (string.IsNullOrEmpty(downloadUrl))
            metadataReadable = false;
        var fileName = metadataReadable
            ? Core.Downloads.DownloadPolicy.SanitizeFileName(suggested)
            : string.Empty;
        var dangerous = !metadataReadable
            || Core.Downloads.DownloadPolicy.RequiresExplicitConfirmation(downloadUrl, fileName);
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
            return;
        }
        // 审计第六轮（2026-10-03）：放行后登记在途下载，供紧急终止取消——
        // 入口判定只能挡新的副作用请求，已开始的下载不会自行停下。
        if (e.DownloadOperation is { } operation)
        {
            lock (_downloadsLock)
                _trackedDownloads.Add(operation);
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
        // R8-CS-SEC-01（第八轮审计 2026-10-04，P1）：核心返回 RequireConfirmation 时，
        // 出货构建（安装器刻意不写 RequireNavigationConfirmation）此前落到
        // 「非 Allow 即 return false」——不发 NavigationDenied、不弹面板，用户按回车后
        // 浏览器毫无反应。第七轮 B8「本机与内网必须能打开」因此在唯一正典制品上
        // 不可观测。本处只补可见性，不改放行/阻断方向——「出厂启用确认门」还是
        // 「核心不再把本机与内网判高危」属产品决策，见第八轮台账第七节待裁决。
        if (decision is Broker.Decision.RequireConfirmation)
        {
            NavigationDenied?.Invoke(
                "该目标被原生策略核心判为需显式确认，但本构建未启用导航确认门——已按失败闭合取消。");
            return false;
        }
        if (decision is not Broker.Decision.Allow allow)
        {
            NavigationDenied?.Invoke("导航裁决无法解析——已按失败闭合取消。");
            return false;
        }
        if (!_broker.TryConsumeNavigation(allow.Action, _sessionId, _tabId, _documentGeneration, rawUrl, "navigation"))
        {
            // 失效的具体原因（会话/代际、nonce 重放、桥不可用）由 broker 侧以审计码留痕
            NavigationDenied?.Invoke("授权已失效或无法兑换（会话变化、重放或策略更新）——导航被取消。");
            return false;
        }

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

namespace Aegis.Windows.Chrome;

using System;
using System.Threading.Tasks;
using Aegis.Windows.Broker;
using Aegis.Windows.Core.Tabs;
using Aegis.Windows.WebView;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

/// <summary>单标签的 UI 侧运行时（ADR-009 D2：每标签一 WebView 实例——
/// 切换即可见性切换，页面状态/滚动/表单天然保留——架构性修复 Python 栈
/// 「切标签全量重载丢状态」缺陷）。
/// 安全边界不变：导航/新窗口/下载/权限全部经该标签自己的 HostWebView→
/// Broker 决策（ADR-002/003）；本类只做事件转发，不拥有策略。</summary>
public sealed class TabRuntime : IDisposable
{
    private bool _disposed;

    /// <summary>目标环境（正常=共享；InPrivate=独立用户目录）。Chrome 调用方
    /// 在创建后以对应环境 EnsureCoreWebView2Async。</summary>
    private Microsoft.Web.WebView2.Core.CoreWebView2Environment? _env;

    public TabRuntime(BrowserPolicyBroker broker, Tab tab, Microsoft.Web.WebView2.Core.CoreWebView2Environment? environment = null)
    {
        Tab = tab;
        _env = environment;
        var sessionId = $"s-{tab.TabId}";
        Host = new HostWebView(broker, sessionId, tab.TabId);
        // Source 不在构造期设置——改用显式 EnsureCoreWebView2Async(自定义环境) 初始化
        //（这样才能注入安全 DNS 等环境参数）。真实目标地址由 Chrome 在
        // CoreWebView2InitializationCompleted 里映射/就绪后导航（见 MainWindow.CreateRuntime）。
        Control = new WebView2();
    }

    public Tab Tab { get; }

    /// <summary>该标签的策略交互封装（确认审批/会话销毁——每标签独立 session）。</summary>
    public HostWebView Host { get; }

    /// <summary>该标签的 WebView2 控件（由 Chrome 容器持有视觉树归属）。</summary>
    public WebView2 Control { get; }

    /// <summary>导航完成（错误页/地址栏同步的 UI 数据源——isSuccess=false 时不静默）。</summary>
    public event Action<bool, CoreWebView2WebErrorStatus>? NavigationCompleted;

    /// <summary>导航开始（加载指示条显示的触发源）。</summary>
    public event Action? NavigationStarted;

    /// <summary>M3 下载确认请求转发（危险扩展——chrome 弹确认对话框）。</summary>
    public event Func<string, string, bool>? DownloadConfirmationRequested
    {
        add => Host.DownloadConfirmationRequested += value;
        remove => Host.DownloadConfirmationRequested -= value;
    }

    /// <summary>target=_blank/window.open 请求转发：由 MainWindow 在现有标签条
    /// 中新建标签（不创建独立弹窗）。</summary>
    public event Action<string>? NewWindowRequested
    {
        add => Host.NewWindowRequested += value;
        remove => Host.NewWindowRequested -= value;
    }

    /// <summary>M3 下载启动通知（反馈条显示）。</summary>
    public event Action<string, bool>? DownloadStarted;

    /// <summary>M4 下载管理面板数据源：授权通过的 DownloadOperation 转交
    /// （dangerous=经用户显式确认的危险扩展下载）。</summary>
    public event Action<CoreWebView2DownloadOperation, bool>? DownloadOperationStarted;

    /// <summary>CoreWebView2 就绪后挂接安全事件与页面事件（每标签一次）。</summary>
    public void OnCoreReady(CoreWebView2 coreWebView2)
    {
        Host.WireEvents(coreWebView2);
        coreWebView2.NavigationStarting += (_, _) => NavigationStarted?.Invoke();
        coreWebView2.DownloadStarting += (_, e) =>
        {
            try
            {
                var dangerous = Core.Downloads.DownloadPolicy.RequiresExplicitConfirmation(
                    e.DownloadOperation?.Uri ?? string.Empty,
                    System.IO.Path.GetFileName(e.DownloadOperation?.ResultFilePath ?? string.Empty));
                DownloadStarted?.Invoke(
                    System.IO.Path.GetFileName(e.DownloadOperation?.ResultFilePath ?? string.Empty),
                    dangerous);
                if (e.DownloadOperation is { } operation)
                    DownloadOperationStarted?.Invoke(operation, dangerous);
            }
            catch
            {
                // 通知失败不影响下载
            }
        };
        coreWebView2.DocumentTitleChanged += (_, _) =>
            Tab.Title = coreWebView2.DocumentTitle;
        coreWebView2.NavigationCompleted += (_, args) =>
        {
            Tab.Url = coreWebView2.Source ?? Tab.Url;
            NavigationCompleted?.Invoke(args.IsSuccess, args.WebErrorStatus);
            // 每站点缩放：导航离开前记住当前站点缩放（Ctrl+滚轮由 WebView2 原生调整）；
            // 导航到新站点时应用其记忆值。
            var host = Uri.TryCreate(coreWebView2.Source, UriKind.Absolute, out var hu)
                ? hu.Host
                : null;
            if (host is not null)
            {
                if (_lastZoomHost is not null && _lastZoomHost != host)
                    Core.Tabs.ZoomStore.Set(_lastZoomHost, Control.ZoomFactor);
                _lastZoomHost = host;
                var zoom = Core.Tabs.ZoomStore.Get(host);
                if (Math.Abs(Control.ZoomFactor - zoom) > 0.001)
                    Control.ZoomFactor = zoom;
                // 站点图标（缓存命中即时；未命中异步抓取后回填）
                var hostCapture = host;
                _ = Core.Favicons.FaviconService.Get(hostCapture, icon =>
                {
                    if (icon is not null)
                        Tab.Icon = icon;
                });
            }
        };
    }

    private string? _lastZoomHost;

    /// <summary>以指定环境初始化（正常=共享；InPrivate=独立用户目录）。
    /// 调用方 fire-and-forget；完成后触发 CoreWebView2InitializationCompleted。</summary>
    public async Task InitAsync()
    {
        var env = _env ?? await WebView.WebViewEnvironment.SharedAsync();
        await Control.EnsureCoreWebView2Async(env);
    }

    /// <summary>重置当前站点缩放到 100%（Ctrl+0）。</summary>
    public void ResetZoom()
    {
        var host = Uri.TryCreate(Control.Source?.ToString(), UriKind.Absolute, out var u)
            ? u.Host
            : null;
        if (host is not null)
        {
            Core.Tabs.ZoomStore.Set(host, 1.0);
            Control.ZoomFactor = 1.0;
        }
    }


    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        // 安全顺序（Android P2-9 教训）：调用方必须已将 Control 从视觉树摘除，
        // 再 dispose（destroy 先于 detach 会拒绝释放 Chromium 资源）。
        Host.Dispose();
        Control.Dispose();
    }
}

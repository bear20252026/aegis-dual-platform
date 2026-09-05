namespace Aegis.Windows.Chrome;

using System;
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

    public TabRuntime(BrowserPolicyBroker broker, Tab tab, string initialUrl)
    {
        Tab = tab;
        var sessionId = $"s-{tab.TabId}";
        Host = new HostWebView(broker, sessionId, tab.TabId);
        // 虚拟主机地址（NTP/画板）先在构造期落在 about:blank——WebView2 控件需要
        // **非 null 的 Source 才会 eager 初始化 CoreWebView2**；设 null 会让控件永不
        // 初始化（首页空白、无安全日志——上线复现实证）。真实 NTP 目标在 Chrome 侧
        // 映射虚拟主机后再导航（见 MainWindow.CreateRuntime）。
        Control = new WebView2
        {
            Source = Chrome.Ntp.NtpAssets.IsVirtualHostUrl(initialUrl)
                ? new Uri("about:blank")
                : ResolveInitialUri(initialUrl),
        };
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
        };
    }

    /// <summary>初始 URL 解析：空/非法一律回退 about:blank（恢复的 URL 若被篡改，
    /// 导航仍会在 broker 层被拒绝——此处只保证控件初始化不抛异常）。</summary>
    private static Uri ResolveInitialUri(string url) =>
        !string.IsNullOrWhiteSpace(url) && Uri.TryCreate(url, UriKind.Absolute, out var uri)
            ? uri
            : new Uri("about:blank");

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

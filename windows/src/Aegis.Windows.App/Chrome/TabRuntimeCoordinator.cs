namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Tabs;

/// <summary>协调 MainWindow 中全部 TabRuntime 的初始化/关闭/延迟导航——
/// 快照 + 令牌 + 视觉树校验的加固层。以适配器方式包住现有 CreateRuntime/
/// OnTabClosed/OnTabSwitched 的控制流，不触碰策略逻辑。</summary>
public sealed class TabRuntimeCoordinator : IDisposable
{
    private readonly Dictionary<string, TabRuntimeLifetime> _lifetimes = new();
    private readonly Dictionary<string, TabRuntime> _runtimes;
    private readonly Panel _host;

    /// <summary>虚拟主机（NTP/Geo）首帧导航有界重试**耗尽**时触发——主窗口借此
    /// 停止加载条并展示明确错误（否则瞬态抑制会让加载条永久旋转）。</summary>
    public event Action<string, Microsoft.Web.WebView2.Core.CoreWebView2WebErrorStatus>? NtpNavigationFailed;

    public TabRuntimeCoordinator(
        Dictionary<string, TabRuntime> runtimes,
        Panel host)
    {
        _runtimes = runtimes ?? throw new ArgumentNullException(nameof(runtimes));
        _host = host ?? throw new ArgumentNullException(nameof(host));
    }

    /// <summary>创建运行时并加入视觉树（不导航——导航由初始化完成回调/调用方驱动）。</summary>
    public TabRuntimeLifetime Create(BrowserPolicyBroker broker, Tab tab)
    {
        var runtime = new TabRuntime(broker, tab);
        var lifetime = new TabRuntimeLifetime(runtime);
        _runtimes[tab.TabId] = runtime;
        _lifetimes[tab.TabId] = lifetime;
        _host.Children.Add(runtime.Control);
        lifetime.InitializeAsync(ex => Core.Security.SecurityLog.Write(
            $"[init] 标签 {tab.TabId} 初始化异常: {ex.GetType().Name}: {ex.Message}"));
        return lifetime;
    }

    /// <summary>关闭标签：先从视觉树摘除，再释放运行时。</summary>
    public void Close(string tabId)
    {
        if (!_runtimes.TryGetValue(tabId, out var runtime))
            return;
        _host.Children.Remove(runtime.Control);
        _runtimes.Remove(tabId);
        if (_lifetimes.Remove(tabId, out var lifetime))
        {
            try { lifetime.Close(); }
            catch (Exception ex) { Core.Security.SecurityLog.Write($"[tab] 标签 {tabId} 销毁容错: {ex.GetType().Name}: {ex.Message}"); }
        }
        else
        {
            try { runtime.Dispose(); }
            catch (Exception ex) { Core.Security.SecurityLog.Write($"[tab] 标签 {tabId} 销毁容错: {ex.GetType().Name}: {ex.Message}"); }
        }
    }

    /// <summary>休眠：从视觉树摘除并按快照释放（复用关闭生命周期）。</summary>
    public void Sleep(string tabId)
    {
        if (!_runtimes.TryGetValue(tabId, out var runtime))
            return;
        _host.Children.Remove(runtime.Control);
        _runtimes.Remove(tabId);
        if (_lifetimes.Remove(tabId, out var lifetime))
        {
            try { lifetime.Close(); }
            catch (Exception ex) { Core.Security.SecurityLog.Write($"[tab] 标签 {tabId} 休眠销毁容错: {ex.GetType().Name}: {ex.Message}"); }
        }
        else
        {
            try { runtime.Dispose(); }
            catch (Exception ex) { Core.Security.SecurityLog.Write($"[tab] 标签 {tabId} 休眠销毁容错: {ex.GetType().Name}: {ex.Message}"); }
        }
    }

    /// <summary>延迟导航：执行前重新校验快照中的 runtime 引用、令牌与窗口状态。</summary>
    public void PostDelayedNavigation(string tabId, string url, bool windowIsAlive)
    {
        if (!_lifetimes.TryGetValue(tabId, out var lifetime))
        {
            // 该标签在延迟前已被销毁——直接丢弃（避免在已释放控件上设 Source）
            return;
        }
        if (lifetime.IsDisposed || lifetime.CancellationToken.IsCancellationRequested)
            return;
        var runtime = lifetime.Runtime;
        // ApplicationIdle：在所有启动/渲染工作安顿后再导航，确保
        // SetVirtualHostNameToFolderMapping 已传播到渲染进程。单次 Normal
        // 优先级 BeginInvoke 在启动争用下会早于映射传播 → ntp.aegis.local
        // 解析失败 → WebView2 呈现纯文本错误文档（首页"文档样纯文字"根因）。
        Application.Current?.Dispatcher?.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(() =>
        {
            if (!ValidateNavigationTarget(tabId, runtime, lifetime, windowIsAlive))
                return;
            if (!NtpAssets.IsVirtualHostUrl(url))
            {
                SafeNavigate(runtime, url);
                return;
            }
            NavigateVirtualHostWithRetry(tabId, runtime, lifetime, url, windowIsAlive, remaining: 4);
        }));
    }

    private const int VirtualHostRetryDelayMs = 50;

    /// <summary>虚拟主机导航 + 失败重试：首帧若因映射未传播而 ConnectionAborted
    ///（IsSuccess=false），稍后重试——重试时映射必然已就绪。有界重试，绝不无限循环。
    /// 短间隔减少内部错误文档的驻留窗口。</summary>
    private void NavigateVirtualHostWithRetry(
        string tabId, TabRuntime runtime, TabRuntimeLifetime lifetime,
        string url, bool windowIsAlive, int remaining)
    {
        if (!ValidateNavigationTarget(tabId, runtime, lifetime, windowIsAlive))
            return;
        var core = runtime.Control.CoreWebView2;
        if (core is null)
            return;
        EventHandler<Microsoft.Web.WebView2.Core.CoreWebView2NavigationCompletedEventArgs> handler = null!;
        handler = (_, e) =>
        {
            core.NavigationCompleted -= handler;
            if (e.IsSuccess)
                return;
            if (remaining <= 0)
            {
                Core.Security.SecurityLog.Write($"[ntp] 标签 {tabId} 虚拟主机导航失败且重试耗尽: {e.WebErrorStatus}");
                // 通知 UI：重试已放弃——由主窗口停止加载条并展示错误（否则
                // 瞬态抑制会让加载条永久旋转、用户无从知晓页面失败）。
                NtpNavigationFailed?.Invoke(tabId, e.WebErrorStatus);
                return;
            }
            // 延迟后重试（映射传播通常在下一次导航前完成）
            var timer = new DispatcherTimer(DispatcherPriority.Background)
            {
                Interval = TimeSpan.FromMilliseconds(VirtualHostRetryDelayMs),
            };
            var localTimer = timer;
            timer.Tick += (_, _) =>
            {
                localTimer.Stop();
                NavigateVirtualHostWithRetry(tabId, runtime, lifetime, url, windowIsAlive, remaining - 1);
            };
            timer.Start();
        };
        core.NavigationCompleted += handler;
        try
        {
            runtime.Control.Source = new Uri(url);
        }
        catch (Exception)
        {
            core.NavigationCompleted -= handler;
        }
    }

    /// <summary>导航前快照校验：窗口存活、runtime 仍是当前对象、未销毁、控件有效。</summary>
    private bool ValidateNavigationTarget(
        string tabId, TabRuntime runtime, TabRuntimeLifetime lifetime, bool windowIsAlive)
    {
        if (!windowIsAlive)
            return false;
        // 二次校验：快照引用仍是最新的、控件仍在本窗口视觉树中
        if (!_runtimes.TryGetValue(tabId, out var current) || !ReferenceEquals(current, runtime))
            return false;
        if (lifetime.IsDisposed || lifetime.CancellationToken.IsCancellationRequested)
            return false;
        if (runtime.Control.CoreWebView2 is null || runtime.Control.Parent is null)
            return false;
        return true;
    }

    private static void SafeNavigate(TabRuntime runtime, string url)
    {
        try { runtime.Control.Source = new Uri(url); }
        catch (Exception) { /* 竞态：安全丢弃 */ }
    }

    public void Dispose()
    {
        foreach (var lifetime in _lifetimes.Values)
        {
            try { lifetime.Dispose(); }
            catch (Exception) { }
        }
        _lifetimes.Clear();
    }
}
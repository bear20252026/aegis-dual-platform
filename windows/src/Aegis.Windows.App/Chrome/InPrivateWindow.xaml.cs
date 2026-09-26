namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using Aegis.Windows.Broker;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

/// <summary>InPrivate 无痕窗口（P1——对齐 Edge）：每窗口独立临时 WebView2 环境
///（隔离 cookie/缓存，多窗口互不共享），多标签；不写历史、不写会话、不落盘
/// 任何数据；全部关闭后清理临时目录（引用计数）。导航仍全量经 Broker 决策
///（无桥架构不变）；NTP 宿主桥同样接入（引擎/壁纸可用——书签/历史/导入/会话
/// 恢复以空数据 fail-closed，不读真实用户数据）。
/// runtime 生命周期（创建/关闭/延迟导航重试）复用 TabRuntimeCoordinator——
/// 与主窗口同一套快照+令牌+视觉树校验（此前本窗口自维护一份漂移副本）。</summary>
public partial class InPrivateWindow : Window
{
    private readonly BrowserPolicyBroker _broker = new();
    private readonly TabManager _tabs = new();
    private readonly Dictionary<string, TabRuntime> _runtimes = new();
    private TabRuntimeCoordinator _runtimeCoordinator = null!;
    private string? _activeTabId;
    private bool _suppressSelection;
    private bool _closed;
    private WebView.InPrivateEnvironmentLease? _environmentLease;
    // 租约获取串行化门闩——??= 与 await 非原子（见 GetLeaseAsync）
    private readonly System.Threading.SemaphoreSlim _leaseGate = new(1, 1);
    // 引擎偏好构造时取一次（此后不再读盘——地址栏每次回车同步 IO 已移除）
    private readonly string _engineKey;

    private const string HomeUrl = Ntp.NtpAssets.Url;

    /// <summary>CS-224：引擎由打开方传入（主窗已持有 settings 快照）——
    /// 无痕窗口不再每窗同步读一次 settings.json；直接启动等无参路径保留
    /// 读盘兜底。</summary>
    public InPrivateWindow(string? searchEngine = null)
    {
        InitializeComponent();
        if (searchEngine is not null && UrlNormalizer.EngineUrls.ContainsKey(searchEngine))
            _engineKey = searchEngine;
        else
        {
            try
            {
                _engineKey = Core.Settings.AppSettings.Load(
                    Core.Settings.AppSettings.DefaultPath).SearchEngine;
            }
            catch (Exception)
            {
                _engineKey = UrlNormalizer.DefaultEngine;
            }
        }
        _runtimeCoordinator = new TabRuntimeCoordinator(_runtimes, WebViewHost);
        _tabs.TabOpened += CreateRuntime;
        _tabs.TabClosed += OnTabClosed;
        _tabs.TabSwitched += OnTabSwitched;
        TabStrip.ItemsSource = _tabs.Tabs;
        _tabs.NewTab(HomeUrl);
    }

    private async void CreateRuntime(Tab tab)
    {
        try
        {
            var lease = await GetLeaseAsync();
            if (_closed)
            {
                // 等待环境期间窗口已关闭——立即归还租约，不再挂载控件
                if (ReferenceEquals(_environmentLease, lease))
                    _environmentLease = null;
                lease.Dispose();
                return;
            }
            // 创建+挂载+初始化（异常观察）统一走协调器；无痕隔离环境经参数注入
            var runtime = _runtimeCoordinator
                .Create(_broker, tab, lease.Environment, isPrivate: true)
                .Runtime;
            runtime.Control.CoreWebView2InitializationCompleted += (_, e) =>
            {
                if (!e.IsSuccess || _closed || !_runtimes.ContainsKey(tab.TabId))
                    return;
                var core = runtime.Control.CoreWebView2;
                Ntp.NtpAssets.BindVirtualHosts(core);
                runtime.OnCoreReady(core);
                WireNtpBridge(runtime, core);
                if (Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
                {
                    // 延迟导航（映射传播等待+失败重试）同样复用协调器——
                    // 执行前重新校验 runtime 引用/令牌/窗口存活
                    _runtimeCoordinator.PostDelayedNavigation(
                        tab.TabId, tab.Url, () => !_closed && IsLoaded);
                }
                else
                {
                    TabRuntime.Navigate(runtime, tab.Url);
                }
            };
            runtime.NavigationCompleted += (_, _) => Dispatcher.BeginInvoke(() => SyncAddressBar(tab));
        }
        catch (Exception ex)
        {
            Core.Security.SecurityLog.Write(
                $"[inprivate] 标签 {tab.TabId} 初始化失败: {ex.GetType().Name}: {ex.Message}");
        }
    }

    /// <summary>获取（或复用）无痕环境租约。`??=` 与 await 非原子——启动期
    /// 快速二连开标签时两路 await 都创建环境，后完成者的租约被 `??=` 丢弃
    /// 且永不 Dispose（临时目录永久残留），故以门闩串行化。</summary>
    private async Task<WebView.InPrivateEnvironmentLease> GetLeaseAsync()
    {
        await _leaseGate.WaitAsync();
        try
        {
            _environmentLease ??= await WebView.WebViewEnvironment.InPrivateAsync();
            return _environmentLease;
        }
        finally
        {
            _leaseGate.Release();
        }
    }

    /// <summary>NTP 宿主桥（与主窗口同顶层门禁）。复用 NtpBridgeFactory.CreatePrivate——
    /// 引擎/壁纸可用，书签/历史/导入/恢复空数据 fail-closed（不读真实用户数据）。
    /// 此前在此手写 15 参数 Services——与工厂漂移，现已收敛。</summary>
    private void WireNtpBridge(TabRuntime runtime, CoreWebView2 core)
    {
        var ntp = Ntp.NtpBridgeFactory.CreatePrivate(runtime, _engineKey);
        core.WebMessageReceived += (_, ev) =>
        {
            try
            {
                if (!Ntp.NtpAssets.IsTopLevelNtpDocument(core))
                    return;
                ntp.TryHandle(
                    ev.Source, ev.WebMessageAsJson,
                    result =>
                    {
                        try
                        {
                            core.PostWebMessageAsJson(
                                System.Text.Json.JsonSerializer.Serialize(result));
                        }
                        catch (Exception)
                        {
                            // 发送方已销毁——响应无处可达，静默丢弃
                        }
                    },
                    // CS-031：导入 I/O 移出 UI 线程，完成后回投 UI 线程注入响应
                    action => Dispatcher.BeginInvoke(action));
            }
            catch (Exception ex)
            {
                Core.Security.SecurityLog.Write(
                    $"[inprivate][ntp] 消息处理异常: {ex.GetType().Name}: {ex.Message}");
            }
        };
    }

    private void OnTabClosed(string tabId) => _runtimeCoordinator.Close(tabId);

    private void OnTabSwitched(Tab tab)
    {
        _activeTabId = tab.TabId;
        foreach (var pair in _runtimes)
        {
            var on = pair.Key == _activeTabId;
            System.Windows.Controls.Panel.SetZIndex(pair.Value.Control, on ? 5 : 0);
            pair.Value.Control.Visibility = on ? Visibility.Visible : Visibility.Collapsed;
            pair.Value.Control.IsHitTestVisible = on;  // CS-177：对齐 MainWindow 切换口径
        }
        WebViewHost.UpdateLayout();
        SyncAddressBar(tab);
        _suppressSelection = true;
        TabStrip.SelectedItem = tab;
        _suppressSelection = false;
    }

    private void SyncAddressBar(Tab tab)
    {
        if (!AddressBar.IsKeyboardFocused)
            AddressBar.Text = tab.Url;
    }

    private void NewTab_Click(object sender, RoutedEventArgs e) => _tabs.NewTab(HomeUrl);

    private void TabClose_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.FrameworkElement fe
            && (fe.Tag as string ?? (fe.DataContext as Tab)?.TabId) is { } id)
            _tabs.CloseTab(id);
    }

    private void TabStrip_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressSelection || TabStrip.SelectedItem is not Tab tab)
            return;
        _tabs.SwitchTo(tab.TabId);
    }

    private void NavigateFromAddressBar()
    {
        var target = UrlNormalizer.Normalize(AddressBar.Text, _engineKey);
        if (target is null || _activeTabId is null || !_runtimes.TryGetValue(_activeTabId, out var rt))
            return;
        TabRuntime.Navigate(rt, target);
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }

    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e) =>
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;

    private void Back_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
            r.Control.GoBack();
    }
    private void Forward_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
            r.Control.GoForward();
    }
    private void Refresh_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
            r.Control.Reload();
    }

    private void CloseWindow_Click(object sender, RoutedEventArgs e) => Close();

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // Esc = 停止加载（浏览器惯例）——不再直接关闭整个无痕窗口
        //（误按丢全部标签）；窗口关闭走 ✕。
        if (e.Key == Key.Escape)
        {
            if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
                r.Control.Stop();
            e.Handled = true;
            return;
        }
        // CS-223：与主窗常用快捷键对齐——此前无痕窗口无键盘操作路径
        switch (e.Key)
        {
            case Key.L when e.KeyboardDevice.Modifiers == System.Windows.Input.ModifierKeys.Control:
                AddressBar.Focus();
                AddressBar.SelectAll();
                e.Handled = true;
                return;
            case Key.T when e.KeyboardDevice.Modifiers == System.Windows.Input.ModifierKeys.Control:
                _tabs.NewTab(HomeUrl);
                e.Handled = true;
                return;
            case Key.W when e.KeyboardDevice.Modifiers == System.Windows.Input.ModifierKeys.Control:
                if (_activeTabId is not null)
                    _tabs.CloseTab(_activeTabId);
                e.Handled = true;
                return;
        }
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _closed = true;
        // 全部 runtime 经协调器统一销毁（先摘视觉树再释放——与主窗口同序）
        _runtimeCoordinator.Dispose();
        _runtimes.Clear();
        _broker.Dispose();
        _environmentLease?.Dispose();
        _environmentLease = null;
    }
}

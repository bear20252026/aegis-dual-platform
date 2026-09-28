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
    // CS-291（2026-09-26 审计）：无痕窗 broker 复用进程级共享 KillSwitch——
    // 此前每窗独立开关，设置窗触发的紧急终止对无痕窗口完全失效（fail-open）
    private readonly BrowserPolicyBroker _broker = new(killSwitch: KillSwitch.Shared);
    private readonly TabManager _tabs = new();
    private readonly Dictionary<string, TabRuntime> _runtimes = new();
    private TabRuntimeCoordinator _runtimeCoordinator = null!;
    // CS-295（2026-09-26 审计）：导航确认面板控制器（与主窗同款——确认门下
    // 此前本窗口零订阅 NavigationConfirmationRequested，导航被静默取消）
    private ApprovalPanelController _approval = null!;
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
        // CS-295：确认面板装配（与主窗同构——XAML 已补 ApprovalOverlay）
        _approval = new ApprovalPanelController(
            ApprovalOverlay, ApprovalOrigin, ApprovalPath, ApprovalScope, ApprovalExpiry,
            ApprovalDenyButton,
            SetNavigationControlsEnabled,
            tabId => _runtimes.TryGetValue(tabId, out var runtime) ? runtime : null,
            ShowRejection);
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
                // CS-281：此订阅为每标签一次性初始化回调，生命周期与 runtime
                // 对象一致（随 runtime 释放整体回收）——无需显式退订
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
            // CS-295：确认门事件接线（与主窗同口径——面板状态由控制器唯一持有）
            runtime.Host.NavigationConfirmationRequested += (_, e) => _approval.Request(tab.TabId, e);
            runtime.Host.NavigationConfirmationResolved += (_, _) => _approval.Resolved();
            // CS-292（2026-09-26 审计）：target=_blank/window.open 链接——主窗有
            // 订阅而无痕窗此前零订阅（HostWebView 一律 Handled 后转发，无人接
            // 收即点击无任何反应）；与主窗同口径：公网/本机地址放行新建标签
            runtime.NewWindowRequested += targetUrl =>
            {
                if (!CanOpenNewWindowLink(targetUrl))
                {
                    Core.Security.SecurityLog.Write(
                        $"[inprivate] 已拒绝打开新窗口链接（非公网/本机地址）: {Core.Security.UrlRedactor.Redact(targetUrl)}");
                    return;
                }
                _tabs.NewTab(targetUrl);
            };
            // CS-294（2026-09-26 审计）：危险扩展下载确认——此前零订阅者走
            // fail-closed 分支被静默取消，用户看不到任何提示；提供与主窗同款
            // 确认对话框（窗口已关闭仍 fail-closed 拒绝）
            runtime.DownloadConfirmationRequested += (downloadUrl, fileName) =>
            {
                if (!IsLoaded)
                    return false;
                return MessageBox.Show(
                    this,
                    $"此文件的类型可能存在风险，是否允许下载？\n\n文件：{fileName}\n来源：{downloadUrl}",
                    "下载确认",
                    MessageBoxButton.YesNo,
                    MessageBoxImage.Warning) == MessageBoxResult.Yes;
            };
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
            pair.Value.Control.IsEnabled = on;         // CS-327（2026-09-26 审计）：对齐主窗四属性口径
        }
        WebViewHost.UpdateLayout();
        SyncAddressBar(tab);
        // CS-284：SelectionChanged 回调同步抛出时抑制标志必须复位
        _suppressSelection = true;
        try
        {
            TabStrip.SelectedItem = tab;
        }
        finally
        {
            _suppressSelection = false;
        }
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

    /// <summary>CS-292：新窗口链接放行判定（与主窗 NewWindowRequested 同口径）。
    /// 提纯 internal 直测——公网 host 或本机/hosts 映射到本机的域名放行，
    /// 非法协议/内网/环回拒绝（安全约束——本机除外）。</summary>
    internal static bool CanOpenNewWindowLink(string? url) =>
        Core.UrlSafety.CanOpenHttpUrl(url);

    // —— CS-295：导航确认面板（控制器逻辑与主窗共用单源） ——

    private void ApprovalAllow_Click(object sender, RoutedEventArgs e) => _approval.Allow();

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e) => _approval.Deny();

    private void SetNavigationControlsEnabled(bool isEnabled)
    {
        AddressBar.IsEnabled = isEnabled;
        BackButton.IsEnabled = isEnabled;
        ForwardButton.IsEnabled = isEnabled;
        RefreshButton.IsEnabled = isEnabled;
    }

    private void ShowRejection(string message)
    {
        ErrorPage.Text = message;
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // CS-295：确认面板打开时 Esc = 拒绝（与主窗同语义——优先于停止加载）
        if (_approval.IsVisible && e.Key == Key.Escape)
        {
            _approval.Deny();
            e.Handled = true;
            return;
        }
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

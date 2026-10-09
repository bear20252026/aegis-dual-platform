namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Linq;
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
    // 审计第六轮（2026-10-03）：同款模式补共享黑名单持有者——本窗此前只共享
    // KillSwitch 不共享 denylist，威胁订阅源刷新永不下发到无痕窗口，已知恶意
    // host 在隐私路径照常导航且 OnWebResourceRequested 不 403（与 CS-291 修复
    // 前同一缺陷类：修了一个共享字段，漏了同文件的另一个）
    private readonly BrowserPolicyBroker _broker = new(
        blockedHosts: SharedBlockedHosts.Shared,
        killSwitch: KillSwitch.Shared);
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
    // CS-364（2026-10-01 审计）：租约工厂注入缝——STA 冒烟测试注入必败工厂，
    // 构造/关闭路径不再拉起真实 WebView2 环境（生产恒走 InPrivateAsync）
    private readonly Func<Task<WebView.InPrivateEnvironmentLease>> _leaseFactory;
    // 引擎偏好构造时取一次（此后不再读盘——地址栏每次回车同步 IO 已移除）
    private readonly string _engineKey;
    // CS-402（2026-10-02 审计）：KillSwitch 常驻横幅订阅句柄（Window_Closing 解绑）
    private readonly Action _killSwitchEngagedHandler;

    private const string HomeUrl = Ntp.NtpAssets.Url;

    /// <summary>CS-224：引擎由打开方传入（主窗已持有 settings 快照）——
    /// 无痕窗口不再每窗同步读一次 settings.json；直接启动等无参路径保留
    /// 读盘兜底。</summary>
    public InPrivateWindow(string? searchEngine = null)
        : this(searchEngine, leaseFactoryForTests: null)
    {
    }

    /// <summary>CS-364：internal 测试构造（leaseFactoryForTests 注入假租约工厂
    /// ——冒烟测试不创建真实 WebView2 环境与浏览器进程）。</summary>
    internal InPrivateWindow(string? searchEngine, Func<Task<WebView.InPrivateEnvironmentLease>>? leaseFactoryForTests)
    {
        _leaseFactory = leaseFactoryForTests ?? WebView.WebViewEnvironment.InPrivateAsync;
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
        // CS-402（2026-10-02 审计）：KillSwitch 触发后的常驻指示（主窗 KillSwitchBanner
        // 同款）——无痕窗 broker 复用进程级共享 KillSwitch（CS-291），设置窗触发的
        // 紧急终止此前对本窗零指示（只见"导航没反应"）。横幅一经显示不再隐藏
        //（Engage 单向——重启恢复）
        _killSwitchEngagedHandler = () => Dispatcher.BeginInvoke(
            () => KillSwitchBanner.Visibility = Visibility.Visible);
        _broker.KillSwitch.Engaged += _killSwitchEngagedHandler;
        if (_broker.KillSwitch.IsEngaged)
            KillSwitchBanner.Visibility = Visibility.Visible;
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
            // CS-384（2026-10-02 审计）：await 期间该标签可能已被关闭——校验
            // tabId 仍在集合，不在则不再 Create（此前对已死标签照样创建 WebView
            // 实例，随后成为孤儿控件）。租约是窗口级共享资源：窗口内已无任何
            // 标签时才归还（其它标签仍在等待/使用同一环境）
            if (_tabs.Tabs.All(t => t.TabId != tab.TabId))
            {
                if (_tabs.Tabs.Count == 0 && ReferenceEquals(_environmentLease, lease))
                {
                    _environmentLease = null;
                    lease.Dispose();
                }
                return;
            }
            // 创建+挂载+初始化（异常观察）统一走协调器；无痕隔离环境经参数注入
            var runtime = _runtimeCoordinator
                .Create(_broker, tab, lease.Environment, isPrivate: true)
                .Runtime;
            runtime.Control.CoreWebView2InitializationCompleted += (_, e) =>
            {
                // CS-358（2026-10-01 审计）：初始化失败留痕（主窗同分支有
                // SecurityLog——此前无痕窗口静默空白不可诊断）
                if (!e.IsSuccess)
                {
                    Core.Security.SecurityLog.Write(
                        $"[inprivate] 标签 {tab.TabId} WebView2 初始化失败: {e.InitializationException?.Message ?? "e.IsSuccess=false（未知原因）"}");
                    return;
                }
                if (_closed || !_runtimes.ContainsKey(tab.TabId))
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
            runtime.NavigationCompleted += (ok, _) => Dispatcher.BeginInvoke(() =>
            {
                // CS-349（2026-10-01 审计）：加载指示收起（主窗同款 LoadingBar）
                LoadingBar.Visibility = Visibility.Collapsed;
                // R8-CS-SEC-05：拒绝/错误横幅此前永不收起——本文件只有置 Visible 的
                // 写点（主窗有 Collapsed 路径），用户被拒一次后横幅就常驻。同款条件收束。
                DismissRejectionOnceNavigated(ok);
                SyncAddressBar(tab);
            });
            // CS-349：导航开始显示不定态加载条（主窗有加载指示——无痕窗此前零反馈）
            runtime.NavigationStarted += () => Dispatcher.BeginInvoke(
                () => LoadingBar.Visibility = Visibility.Visible);
            // CS-295：确认门事件接线（与主窗同口径——面板状态由控制器唯一持有）
            runtime.Host.NavigationConfirmationRequested += (_, e) => _approval.Request(tab.TabId, e);
            runtime.Host.NavigationConfirmationResolved += (_, _) => _approval.Resolved();
            // CS-378（2026-10-02 审计）：策略拒绝原因订阅（主窗同款，参照
            // MainWindow CreateRuntime 的 CS-355 接线）——此前无痕窗零订阅，
            // broker DenyReason 在 HostWebView 内被丢弃（导航只是"无反应"，
            // 零可见反馈）
            runtime.NavigationDenied += msg => Dispatcher.BeginInvoke(() => ShowRejection(msg));
            // CS-292（2026-09-26 审计）：target=_blank/window.open 链接——主窗有
            // 订阅而无痕窗此前零订阅（HostWebView 一律 Handled 后转发，无人接
            // 收即点击无任何反应）；与主窗同口径：公网/本机地址放行新建标签
            runtime.NewWindowRequested += targetUrl =>
            {
                if (!CanOpenNewWindowLink(targetUrl))
                {
                    Core.Security.SecurityLog.Write(
                        $"[inprivate] 已拒绝打开新窗口链接（链路本地/云元数据/保留地址）: {Core.Security.UrlRedactor.Redact(targetUrl)}");
                    return;
                }
                _tabs.NewTab(targetUrl);
            };
            // CS-294（2026-09-26 审计）：危险扩展下载确认——此前零订阅者走
            // fail-closed 分支被静默取消，用户看不到任何提示；提供与主窗同款
            // 确认对话框（窗口已关闭仍 fail-closed 拒绝）
            // CS-370（2026-10-01 审计）：确认对话框单源到 WindowSharedChrome
            //（与主窗共用——此前两窗各持一份同形 MessageBox）
            runtime.DownloadConfirmationRequested += (downloadUrl, fileName) =>
                WindowSharedChrome.ConfirmDangerousDownload(this, downloadUrl, fileName);
        }
        catch (Exception ex)
        {
            Core.Security.SecurityLog.Write(
                $"[inprivate] 标签 {tab.TabId} 初始化失败: {ex.GetType().Name}: {ex.Message}");
        }
    }

    /// <summary>获取（或复用）无痕环境租约。`??=` 与 await 非原子——启动期
    /// 快速二连开标签时两路 await 都创建环境，后完成者的租约被 `??=` 丢弃
    /// 且永不 Dispose（临时目录永久残留），故以门闩串行化。
    /// CS-364：工厂可注入（测试），生产恒为 WebViewEnvironment.InPrivateAsync。</summary>
    private async Task<WebView.InPrivateEnvironmentLease> GetLeaseAsync()
    {
        await _leaseGate.WaitAsync();
        try
        {
            _environmentLease ??= await _leaseFactory();
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

    private void OnTabClosed(string tabId)
    {
        _runtimeCoordinator.Close(tabId);
        // CS-393（2026-10-02 审计）：关掉最后一个标签（CloseTab 返回 null——
        // 集合已空）后窗口滞留空壳——此时关窗（与主窗同口径）
        if (_tabs.Tabs.Count == 0)
            Close();
    }

    private void OnTabSwitched(Tab tab)
    {
        _activeTabId = tab.TabId;
        foreach (var pair in _runtimes)
        {
            // CS-177/327/371：与 MainWindow 切换口径一致——四属性翻转单源
            //（此前两窗各持一份同形实现）
            WindowSharedChrome.ApplyTabVisibility(pair.Value.Control, pair.Key == _activeTabId);
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
        // CS-411（2026-10-02 审计）：与主窗同口径的单源守卫（SecurityLog 留痕 +
        // try/catch 不阻断——此前本窗裸调 CloseTab，库/集合异常直接炸窗）
        if (sender is System.Windows.FrameworkElement fe
            && (fe.Tag as string ?? (fe.DataContext as Tab)?.TabId) is { } id)
            WindowSharedChrome.CloseTabSafely(_tabs, id);
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
    /// 提纯 internal 直测——协议合法且不在保留地址边界内即放行（R8-CS-SEC-06：
    /// 此前判「公网或本机」，把 B8 裁决要求能打开的内网设备一律拒掉）。</summary>
    internal static bool CanOpenNewWindowLink(string? url) =>
        Core.UrlSafety.CanOpenHttpUrl(url);

    // —— CS-295：导航确认面板（控制器逻辑与主窗共用单源） ——

    private void ApprovalAllow_Click(object sender, RoutedEventArgs e) => _approval.Allow();

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e) => _approval.Deny();


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
        // CS-402：解绑 KillSwitch 横幅订阅（横幅句柄不再持有已关窗口）
        _broker.KillSwitch.Engaged -= _killSwitchEngagedHandler;
        // 全部 runtime 经协调器统一销毁（先摘视觉树再释放——与主窗口同序）
        // CS-366（2026-10-01 审计）：_runtimes 清空收敛到协调器 Dispose 单点
        _runtimeCoordinator.Dispose();
        _broker.Dispose();
        _environmentLease?.Dispose();
        _environmentLease = null;
    }
}

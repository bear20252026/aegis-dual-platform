namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using Aegis.Windows.Broker;
using Aegis.Windows.Core;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Security;
using Aegis.Windows.Core.Settings;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

/// <summary>主窗口（受信 chrome UI 域）。Chrome 只提交用户意图和显示结果——
/// 不能绕过 Broker（ADR-002）。远程页面无 native bridge（ADR-003）。
/// M1-T1（ADR-009）：多标签编排——TabManager（领域状态）+ TabRuntime（每标签
/// 一 WebView 实例）；切换即可见性切换，页面状态天然保留；标签条为原生
/// 控件（与页面 DOM 隔离——注入式 UI 成为历史）。</summary>
public partial class MainWindow : Window
{
    private readonly BrowserPolicyBroker _broker;
    private readonly TabManager _tabs;
    private readonly Dictionary<string, TabRuntime> _runtimes = new();
    private TabRuntimeCoordinator _runtimeCoordinator = null!;
    private TabStripDragController _tabDrag = null!;
    private ApprovalPanelController _approval = null!;
    private readonly TabSessionStore _sessionStore;
    private string? _activeTabId;
    private bool _suppressTabSelection;
    private readonly BookmarkStore _bookmarks;
    private readonly HistoryStore _history;
    private readonly AppSettings _settings;
    private readonly Core.Settings.SettingsService _settingsService;
    private HistoryWindow? _historyWindow;
    private BookmarkManagerWindow? _bookmarkManagerWindow;
    private SettingsWindow? _settingsWindow;
    private DownloadsWindow? _downloadsWindow;
    // 源码查看器允许多实例并存——换肤时对仍存活者传播并清理已关闭项
    private readonly List<SourceViewerWindow> _sourceViewerWindows = new();
    private System.Windows.Threading.DispatcherTimer? _feedbackTimer;
    // M4 下载管理面板数据源（跨标签共享——DownloadItem 由 TabRuntime 下载事件注入）
    private readonly System.Collections.ObjectModel.ObservableCollection<Core.Downloads.DownloadItem> _downloads = new();
    private readonly Core.Downloads.DownloadRecordStore _downloadRecords;
    private System.Windows.Threading.DispatcherTimer? _sleepTimer;
    private System.Windows.Threading.DispatcherTimer? _sessionSaveTimer;
    private FindBarController _find = null!;
    private SuggestionController _suggest = null!;
    private Ntp.NtpBridgeFactory _ntpBridgeFactory = null!;
    private Action? _zoomChangedHandler;

    private const string HomeUrl = Chrome.Ntp.NtpAssets.Url;

    // —— 集中管理的 UI 时序/阈值常量（审计修复：此前 150ms/30s/2.5s 等魔法数
    //    散落各处，调整需全文检索） ——
    private const int SleepCheckIntervalSec = 30;     // 后台标签睡眠巡检周期
    private const int FeedbackHideMs = 2500;          // 反馈条自动隐藏
    private const int SessionSaveDebounceMs = 2000;   // 会话落盘防抖（写放大治理）
    private const int SourceFetchTimeoutSec = 15;     // 源码查看抓取超时
    private const int SourceMaxBytes = 5 * 1024 * 1024; // 源码查看大小上限
    private const int BookmarkChipMaxChars = 14;      // 书签栏标题截断

    /// <summary>组合根注入构造：存储/策略/broker 由 App 装配传入（MainWindow 不再
    /// 自建依赖——可注入内存存储、可构造测）。参数校验防误用。</summary>
    public MainWindow(MainWindowDependencies deps)
    {
        _broker = deps.Broker;
        _tabs = deps.Tabs;
        _sessionStore = deps.SessionStore;
        _bookmarks = deps.Bookmarks;
        _history = deps.History;
        _settings = deps.Settings;
        _settingsService = deps.SettingsService;
        _downloadRecords = deps.DownloadRecords;
        InitializeComponent();
        _runtimeCoordinator = new TabRuntimeCoordinator(_runtimes, WebViewHost);
        // 虚拟主机首帧重试耗尽：停止加载条并展示明确错误——瞬态抑制不应让
        // 加载条永久旋转，用户须能感知"虚拟主机资源无法加载"。
        _runtimeCoordinator.NtpNavigationFailed += OnNtpNavigationFailed;
        try { ApplyTheme(_settings.Theme); } catch (Exception ex) { System.Diagnostics.Debug.WriteLine($"ApplyTheme: {ex.Message}"); }
        _tabs.TabOpened += OnTabOpened;
        _tabs.TabClosed += OnTabClosed;
        _tabs.TabSwitched += OnTabSwitched;
        // 上帝对象拆分·第一批：查找条与地址栏建议逻辑外移独立控制器
        //（防抖/后台查询/乱序防护在 SuggestionController，window.find 在 FindBarController）
        _find = new FindBarController(FindBar, FindBox, FindCount, ActiveRuntime);
        _suggest = new SuggestionController(
            AddressBar, SuggestionPopup, SuggestionList,
            _bookmarks, _history, NavigateFromAddressBar);
        // 第二批：NTP 宿主桥 15 项服务委托组装外移工厂（数据服务单源注入）
        _ntpBridgeFactory = new Ntp.NtpBridgeFactory(
            _settings, _settingsService, _bookmarks, _history, _sessionStore,
            RestoreSavedSession, engine => EngineCombo.SelectedValue = engine);
        // 第三批：标签条拖拽排序 + 导航确认面板外移控制器
        _tabDrag = new TabStripDragController(TabStrip, _tabs);
        _approval = new ApprovalPanelController(
            ApprovalOverlay, ApprovalOrigin, ApprovalPath, ApprovalScope, ApprovalExpiry,
            ApprovalDenyButton, SetNavigationControlsEnabled,
            tabId => _runtimes.TryGetValue(tabId, out var runtime) ? runtime : null,
            ShowRejection);
        TabStrip.ItemsSource = _tabs.Tabs;
        RestoreSessionOrStart();
        RefreshBookmarkBar();
        StartThreatFeedRefresh();
        InitEngineCombo();
        ZoomStore.Load(_settings.ZoomByHost);
        _zoomChangedHandler = () => Dispatcher.Invoke(() => _settings.ZoomByHost = ZoomStore.Snapshot());
        ZoomStore.Changed += _zoomChangedHandler;
        // 设置单一事实源：统一持久化 + 刷新运行时 PrivacySettings
        _settingsService.Apply(_settings);
        RestoreWindowState();
        StartSleepTimer();
    }

    /// <summary>设置导航地址的统一容错入口（地址非法/控件已释放时拒绝而不是
    /// 抛异常——地址栏、书签、NTP 桥全部经此）。</summary>
    private static bool SafeNavigate(TabRuntime runtime, string? url)
    {
        if (string.IsNullOrWhiteSpace(url) || !Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return false;
        try
        {
            runtime.Control.Source = uri;
            return true;
        }
        catch (Exception)
        {
            return false;  // 控件已释放/竞态——安全丢弃
        }
    }

    /// <summary>截断标题而不劈开代理对（emoji 等——此前 b.Title[..14] 可把
    /// 双字符字形切成乱码）。</summary>
    private static string TruncateTitle(string title, int maxChars)
    {
        if (title.Length <= maxChars)
            return title;
        var cut = maxChars;
        if (cut > 0 && char.IsHighSurrogate(title[cut - 1]))
            cut--;  // 高代理项必须与低代理项成对——退一位
        return title[..cut] + "…";
    }

    /// <summary>刷新书签栏（书签变更时重载）。</summary>
    public void RefreshBookmarkBar()
    {
        // 防御：样式资源缺失绝不能中断启动（history 回归 V3 教训——FindResource 抛
        // ResourceReferenceKeyNotFoundException，只要有书签就崩）。查不到时跳过样式。
        Style? chip = null;
        try { chip = (Style)FindResource("BookmarkBarButton"); }
        catch (Exception) { System.Diagnostics.Debug.WriteLine("BookmarkBarButton 资源缺失，使用默认按钮样式"); }
        BookmarkBarItems.Items.Clear();
        foreach (var b in _bookmarks.All())
        {
            var btn = new System.Windows.Controls.Button
            {
                Content = TruncateTitle(b.Title, BookmarkChipMaxChars),
                Tag = b.Url,
                ToolTip = b.Url,
                Style = chip,
            };
            btn.Click += (s, e) =>
            {
                if (s is System.Windows.Controls.Button { Tag: string url } && _activeTabId is not null
                    && _runtimes.TryGetValue(_activeTabId, out var rt))
                    SafeNavigate(rt, url);
            };
            BookmarkBarItems.Items.Add(btn);
        }
        BookmarkBar.Visibility = BookmarkBarItems.Items.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void StartSleepTimer()
    {
        _sleepTimer = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(SleepCheckIntervalSec) };
        _sleepTimer.Tick += (_, _) => SleepCheck();
        _sleepTimer.Start();
    }

    /// <summary>搜索引擎下拉项（key + 展示名）。</summary>
    public sealed record EngineOption(string Key, string Name);

    /// <summary>M2：搜索引擎下拉（展示名 + AppSettings 持久化——重启动保持偏好）。</summary>
    private void InitEngineCombo()
    {
        EngineCombo.ItemsSource = UrlNormalizer.EngineOrder
            .Select(k => new EngineOption(k, UrlNormalizer.EngineName(k)))
            .ToList();
        EngineCombo.DisplayMemberPath = nameof(EngineOption.Name);
        EngineCombo.SelectedValuePath = nameof(EngineOption.Key);
        EngineCombo.SelectedValue = _settings.SearchEngine;
    }

    // ================= 深/浅主题（对齐 Edge 明暗外观） =================

    /// <summary>按设置应用浏览器 chrome 主题（dark/light——DynamicResource 色
    /// 刷运行时替换，工具栏/标签/地址栏即时切换；已打开的独立窗口（设置/历史/
    /// 下载/书签管理）同步换肤——此前它们永远深色，浅色模式下割裂）。</summary>
    public void ApplyTheme(string? theme)
    {
        var light = string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        SetBrush("ChromeBackgroundBrush", light ? "#FFF5F5F7" : "#FF101827");
        SetBrush("ButtonOverlayBrush", light ? "#14000000" : "#33FFFFFF");
        SetBrush("ButtonOverlayHoverBrush", light ? "#20000000" : "#4DFFFFFF");
        SetBrush("ButtonOverlayPressedBrush", light ? "#2E000000" : "#66FFFFFF");
        SetBrush("FieldBackgroundBrush", light ? "#FFFFFFFF" : "#1FFFFFFF");
        SetBrush("FieldBorderBrush", light ? "#FFDADCE0" : "#2EFFFFFF");
        SetBrush("SurfaceBrush", light ? "#FFFFFFFF" : "#FF1B2537");
        SetBrush("FieldBorderFocusedBrush", light ? "#FF0B57D0" : "#66FFFFFF");
        SetBrush("TextPrimaryBrush", light ? "#FF1A1A1A" : "#FFFFFFFF");
        SetBrush("TextSecondaryBrush", light ? "#FF5F6368" : "#B3FFFFFF");
        // 补齐子窗口依赖的画刷（默认深色值——各独立窗口资源键与主窗口统一）
        SetBrush("TextMutedBrush", light ? "#FF8A8A8E" : "#6CFFFFFF");
        SetBrush("SegmentedBrush", light ? "#14000000" : "#1FFFFFFF");
        Background = Resources["ChromeBackgroundBrush"] as System.Windows.Media.Brush
                    ?? Core.ThemeColor.ParseBrush(light ? "#FFF5F5F7" : "#FF101827");
        // 传播到已打开的独立窗口
        _historyWindow?.ApplyTheme(theme);
        _bookmarkManagerWindow?.ApplyTheme(theme);
        _downloadsWindow?.ApplyTheme(theme);
        _settingsWindow?.ApplyTheme(theme);
        _sourceViewerWindows.RemoveAll(w => !w.IsLoaded);
        foreach (var viewer in _sourceViewerWindows)
            viewer.ApplyTheme(theme);
    }

    private void SetBrush(string key, string hex) =>
        Resources[key] = Core.ThemeColor.ParseBrush(hex);

    private void Engine_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (EngineCombo.SelectedValue is not string engine)
            return;
        _settings.SearchEngine = engine;
        _settingsService.Apply(_settings);
    }

    /// <summary>M1-T2：威胁黑名单启动快照 + 订阅源后台刷新（对齐 Python 批次 2-1）。
    /// 订阅源经环境变量 AEGIS_THREAT_FEED_URL 配置（M4 移入设置界面）。</summary>
    private void StartThreatFeedRefresh()
    {
        var cachePath = AppPaths.ThreatFeedCachePath;
        var snapshot = ThreatFeedUpdater.LoadCached(cachePath);
        _broker.UpdateBlockedHosts(new BlockedHosts(snapshot));
        SecurityLog.Write($"[threat] 黑名单快照 {snapshot.Count} 条");
        // M4-b：设置窗口优先；环境变量后备（headless/CI 场景）
        var feedUrl = string.IsNullOrWhiteSpace(_settings.ThreatFeedUrl)
            ? Environment.GetEnvironmentVariable("AEGIS_THREAT_FEED_URL")
            : _settings.ThreatFeedUrl;
        if (string.IsNullOrWhiteSpace(feedUrl))
            return;
        var validated = ThreatFeedUpdater.ValidateFeedUrl(feedUrl);
        if (validated is null)
        {
            SecurityLog.Write("[threat] 订阅源非法（仅支持 https）——保持旧快照");
            return;
        }
        Task.Run(() =>
        {
            try
            {
                var count = ThreatFeedUpdater.FetchAndStore(validated, cachePath);
                _broker.UpdateBlockedHosts(new BlockedHosts(
                    ThreatFeedUpdater.LoadCached(cachePath)));
                SecurityLog.Write($"[threat] 订阅源刷新完成：{count} 条域名入黑名单");
            }
            catch (Exception ex)
            {
                SecurityLog.Write($"[threat] 订阅源刷新失败（保持旧快照）: {ex.Message}");
            }
        });
    }

    // ================= 标签生命周期（TabManager 事件 → runtime 管理） =================

    /// <summary>创建标签的 UI 运行时并挂入容器（不激活——激活由 TabSwitched 统一）。</summary>
    private void OnTabOpened(Tab tab) => CreateRuntime(tab, tab.Url);

    private void CreateRuntime(Tab tab, string initialUrl)
    {
        // 日志脱敏：不落 query（token/搜索词）
        Core.Security.SecurityLog.Write(
            $"[tab] 创建标签 {tab.TabId} url={(Uri.TryCreate(initialUrl, UriKind.Absolute, out var u) ? u.GetLeftPart(UriPartial.Authority) + u.AbsolutePath : initialUrl)}");
        var runtime = _runtimeCoordinator.Create(_broker, tab).Runtime;
        runtime.Control.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
            {
                Core.Security.SecurityLog.Write(
                    $"[init] 标签 {tab.TabId} 初始化失败: {e.InitializationException?.Message ?? "e.IsSuccess=false（未知原因）"}");
                return;
            }
            var core = runtime.Control.CoreWebView2;
            Ntp.NtpAssets.BindVirtualHosts(core);
            runtime.OnCoreReady(core);
            // 下载完成 → 持久化记录（大小取自操作对象声明的总字节数——下载
            // 刚启动时目标文件常未创建，此前 FileInfo.Length 直接抛异常被吞，
            // 记录丢失）
            runtime.DownloadOperationStarted += (op, dangerous) =>
            {
                Dispatcher.BeginInvoke(() =>
                {
                    try
                    {
                        var filePath = op?.ResultFilePath ?? "";
                        var size = (long)(op?.TotalBytesToReceive ?? 0);
                        _downloadRecords.Add(
                            System.IO.Path.GetFileName(filePath), filePath,
                            op?.Uri ?? "", size, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
                    }
                    catch (Exception ex)
                    {
                        Core.Security.SecurityLog.Write(
                            $"[download] 记录持久化失败: {ex.GetType().Name}: {ex.Message}");
                    }
                });
            };
            // 虚拟主机地址（NTP/画板）：映射就绪后才导航，且**推迟到下一
            // Dispatcher 周期**——同一调用栈里 SetVirtualHostNameToFolderMapping
            // 后立即导航会因映射尚未传播到渲染进程而 ConnectionAborted
            //（实机复现：点主页能渲染、初始化时同步导航即 abort）。推迟后
            // 与「点主页成功」路径一致。
            if (Chrome.Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
            {
                // 经协调器延迟导航：执行前重新校验 runtime 引用/令牌/窗口状态，
                // 避免在已释放控件上设 Source 抛异常（「新建标签删不掉」防护）。
                _runtimeCoordinator.PostDelayedNavigation(tab.TabId, tab.Url, () => IsLoaded);
            }
            else
            {
                // 普通站点：初始化（含虚拟主机映射）就绪后立即导航。
                // 修复：此前用 else if (!_restoring) 导致会话恢复时普通标签
                // 初始化后不导航（停留在空标签）——恢复与否都应导航。
                SafeNavigate(runtime, tab.Url);
            }
            // M3 新标签页宿主桥：通道绑定到受信 NTP **顶层文档**——远程页面
            // per-origin 关闭 WebMessage，且本桥要求顶层来源就是 ntp.aegis.local
            //（内嵌 iframe 伪装 ntp 来源的请求在顶层门禁处拒绝——ADR-003 无桥
            // 保证的纵深防御）；导航意图回归 NavigationStarting→broker 唯一路径
            var ntp = CreateNtpBridge(runtime);
            core.WebMessageReceived += (_, ev) =>
            {
                // 顶层文档（core.Source）必须是 NTP 虚拟主机；发送来源（ev.Source）
                // 由 NtpBridge 二次校验。二者任一不符即静默忽略——帧内嵌不可达。
                if (!Ntp.NtpAssets.IsTopLevelNtpDocument(core))
                    return;
                try
                {
                    ntp.TryHandle(
                        ev.Source, ev.WebMessageAsJson,
                        result =>
                        {
                            // restoreSession 会同步拆除当前标签（含发送标签）——
                            // core 可能已被释放；响应注入必须容错，绝不抛未处理异常
                            try
                            {
                                core.PostWebMessageAsJson(
                                    System.Text.Json.JsonSerializer.Serialize(result));
                            }
                            catch (Exception)
                            {
                                // 发送标签已随会话重建销毁——响应无处可达，静默丢弃
                            }
                        });
                }
                catch (Exception ex)
                {
                    // 桥内服务（书签/历史 SQLite、导入）异常不得沿 WebMessageReceived
                    // 冒泡成全局未处理异常弹窗——记录后吞掉
                    Core.Security.SecurityLog.Write(
                        $"[ntp] 桥处理异常: {ex.GetType().Name}: {ex.Message}");
                }
            };
        };
        runtime.NavigationCompleted += (ok, status) => OnTabNavigationCompleted(tab.TabId, ok, status);
        // M4 下载管理面板：授权通过的 DownloadOperation 注入共享数据源
        runtime.DownloadOperationStarted += (operation, dangerous) => Dispatcher.Invoke(() =>
        {
            _downloads.Insert(0, new Core.Downloads.DownloadItem(
                operation,
                System.IO.Path.GetFileName(operation.ResultFilePath ?? string.Empty),
                operation.Uri ?? string.Empty,
                dangerous));
        });
        // M1 加载指示接线：导航开始显示不定态条，完成/失败隐藏
        runtime.NavigationStarted += () =>
        {
            if (tab.TabId == _activeTabId)
                LoadingBar.Visibility = Visibility.Visible;
        };
        runtime.Host.NavigationConfirmationRequested += (_, e) => _approval.Request(tab.TabId, e);
        runtime.Host.NavigationConfirmationResolved += (_, _) => _approval.Resolved();
        // target=_blank / window.open 链接：不再静默丢弃，改为验证地址后
        // 在当前窗口新建标签打开（对齐主流浏览器）。公网地址或本机/hosts
        // 映射到本机的域名放行（本地开发访问）；非法协议/内网/环回地址仍拒
        //（安全约束——本机除外）。
        runtime.NewWindowRequested += targetUrl =>
        {
            if (!Core.UrlSafety.CanOpenHttpUrl(targetUrl))
            {
                ShowFeedback("已拒绝打开该链接（非公网/本机地址）", isWarning: true);
                return;
            }
            _tabs.NewTab(targetUrl);
        };
        // M3 危险扩展下载确认（审计补缺——此前 DownloadConfirmationRequested
        // 全仓零订阅者 → 危险下载恒被静默拒绝，该功能形同虚设）。用户显式
        // 确认才放行；窗口已关闭/异常仍 fail-closed 拒绝。
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
        // 视觉树挂载 + 初始化统一由协调器驱动（Create 已完成两者——
        // 显式初始化含安全 DNS 等参数，完成后触发 CoreWebView2InitializationCompleted，
        // 上方处理器负责映射+导航）。
    }

    /// <summary>M3：虚拟主机资源映射与 NTP 顶层文档门禁统一在 NtpAssets
    ///（主窗口与无痕窗口共用单源——此前两份逐行复制漂移）。</summary>

    /// <summary>M3：新标签页宿主桥组装（逻辑在 NtpBridgeFactory——上帝对象
    /// 拆分第二批；保留薄转发以维持 CreateRuntime 内单一装配点）。</summary>
    private Chrome.Ntp.NtpBridge CreateNtpBridge(TabRuntime runtime) =>
        _ntpBridgeFactory.Create(runtime);

    private void OnTabClosed(string tabId)
    {
        _runtimeCoordinator.Close(tabId);
        SaveSession();
    }

    private void OnTabSwitched(Tab tab)
    {
        _activeTabId = tab.TabId;
        tab.LastActivated = DateTime.Now;
        if (tab.IsSleeping)
            WakeTab(tab);  // 睡眠标签激活 → 复活（重建 WebView 实例）
        foreach (var pair in _runtimes)
        {
            var isActive = pair.Key == _activeTabId;
            // WebView2 是 HWND 承载控件：仅切 Visibility 在部分 WPF 版本中
            // 不足以刷新层级。显式控制 Z 序、命中测试和可见性，保证激活
            // 标签永远位于其它标签之上（ApprovalOverlay 的 Z=10 仍保持最顶层）。
            System.Windows.Controls.Panel.SetZIndex(pair.Value.Control, isActive ? 5 : 0);
            pair.Value.Control.Visibility = isActive ? Visibility.Visible : Visibility.Collapsed;
            pair.Value.Control.IsHitTestVisible = isActive;
            pair.Value.Control.IsEnabled = isActive;
        }
        WebViewHost.UpdateLayout();
        SyncAddressBar(tab.Url);
        _suppressTabSelection = true;
        TabStrip.SelectedItem = tab;
        _suppressTabSelection = false;
    }

    private void OnTabNavigationCompleted(string tabId, bool isSuccess, CoreWebView2WebErrorStatus status)
    {
        var tab = _tabs.Tabs.FirstOrDefault(t => t.TabId == tabId);
        if (tab is null)
            return;
        var isActive = tabId == _activeTabId;
        // NTP 虚拟主机映射传播期间可能先收到 ConnectionAborted；协调器已
        // 注册有界重试。不要把这个内部瞬态失败渲染成错误页，否则用户会先
        // 看到乱码/错误文档，随后才跳回主页面。
        if (isActive && !isSuccess
            && Ntp.NtpAssets.IsVirtualHostUrl(tab.Url)
            && status == CoreWebView2WebErrorStatus.ConnectionAborted)
        {
            LoadingBar.Visibility = Visibility.Visible;
            ErrorPagePanel.Visibility = Visibility.Collapsed;
            return;
        }
        if (isActive && !isSuccess && status != CoreWebView2WebErrorStatus.OperationCanceled)
        {
            ErrorPage.Text = $"导航失败：{status}（已拒绝/无法加载）";
            ErrorPagePanel.Visibility = Visibility.Visible;
        }
        else if (isActive)
        {
            ErrorPagePanel.Visibility = Visibility.Collapsed;
        }
        if (isActive)
        {
            LoadingBar.Visibility = Visibility.Collapsed;
            SyncAddressBar(tab.Url);
        }
        // 浏览历史记录（M2 缺口修复——此前仅导入写入，浏览从未落库）：
        // 成功导航 + 历史开关开 + 非内部页（首页/画板/空白页——避免「历史
        // 全被首页占满」）。后台标签完成导航同样记录。
        if (isSuccess && _settings.HistoryEnabled
            && Core.History.HistoryRecorder.IsRecordableUrl(tab.Url))
        {
            _history.Add(tab.Url, tab.Title);
        }
        // 每次导航完成即落盘（对齐 Python 栈崩溃恢复能力——强杀/崩溃后
        // 重启仍可恢复到最后的页面集合，而非仅正常关闭时的快照）
        SaveSession();
    }

    /// <summary>虚拟主机首帧有界重试耗尽（协调器事件）：停止加载条并展示明确
    /// 错误——瞬态抑制只针对映射传播期，重试放弃后必须让用户可见失败。</summary>
    private void OnNtpNavigationFailed(string tabId, CoreWebView2WebErrorStatus status)
    {
        if (tabId != _activeTabId)
            return;  // 仅对激活标签反映 UI 状态
        LoadingBar.Visibility = Visibility.Collapsed;
        ErrorPage.Text = $"首页资源加载失败：{status}（已重试，无法加载）";
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    // ================= 标签条交互 =================

    private void NewTab_Click(object sender, RoutedEventArgs e) => _tabs.NewTab(HomeUrl);

    private void TabClose_Click(object sender, RoutedEventArgs e)
    {
        // tabId 来源：优先按钮 Tag（="{Binding TabId}"）；Tag 未命中时回退到
        // 按钮 DataContext（列表项即 Tab），两者兼取保证关闭可靠触发
        if (sender is not System.Windows.FrameworkElement fe)
            return;
        var tabId = fe.Tag as string
            ?? (fe.DataContext as Core.Tabs.Tab)?.TabId;
        if (string.IsNullOrEmpty(tabId))
            return;
        Core.Security.SecurityLog.Write($"[tab] 请求关闭标签 {tabId}");
        try
        {
            _tabs.CloseTab(tabId);
        }
        catch (Exception ex)
        {
            Core.Security.SecurityLog.Write($"[tab] 关闭标签异常（已捕获，不阻断）: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private void TabStrip_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressTabSelection)
            return;
        if (TabStrip.SelectedItem is Core.Tabs.Tab tab)
            _tabs.SwitchTo(tab.TabId);
    }

    /// <summary>显式标签点击切换（兜底）：自定义 ListBoxItem 模板里同时有
    /// 关闭按钮与 DockPanel 子元素，部分环境下仅靠 SelectionChanged 的
    /// 隐式命中可能失效（表现为「新建了标签但点击切不过去」）。此处直接
    /// 命中标签项即切换，命中关闭按钮则交给其自身的 Click（不动手切换）。</summary>
    private void TabStrip_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        // 记录按下起点——拖拽需超过阈值移动才判定为拖拽（防误触发吞点击）
        _tabDrag.RecordDragStart(e.GetPosition(TabStrip));
        if (TabStrip.InputHitTest(e.GetPosition(TabStrip)) is not DependencyObject hit)
            return;
        var node = hit;
        while (node is not null && node is not System.Windows.Controls.ListBoxItem)
            node = System.Windows.Media.VisualTreeHelper.GetParent(node);
        if (node is not System.Windows.Controls.ListBoxItem item
            || item.DataContext is not Core.Tabs.Tab tab)
            return;
        // 命中关闭按钮（✕）→ 让按钮自己的 Click 处理关闭，不在此切换
        var probe = hit;
        while (probe is not null)
        {
            if (probe is System.Windows.Controls.Button button && ReferenceEquals(button.Tag, tab.TabId))
                return;
            probe = System.Windows.Media.VisualTreeHelper.GetParent(probe);
        }
        _tabs.SwitchTo(tab.TabId);
    }



    private TabRuntime? ActiveRuntime() =>
        _activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r) ? r : null;

    private void ZoomActive(double delta)
    {
        var rt = ActiveRuntime();
        if (rt?.Control.CoreWebView2 is null)
            return;
        var host = Uri.TryCreate(rt.Control.CoreWebView2.Source, UriKind.Absolute, out var u)
            ? u.Host : null;
        // 与 ZoomStore/设置归一同口径（此前会话内允许 0.25、持久化钳 1.0——
        // 缩小后的值重启即被静默重置）
        var z = Math.Clamp(rt.Control.ZoomFactor + delta, TabRuntime.MinZoom, TabRuntime.MaxZoom);
        rt.Control.ZoomFactor = z;
        if (host is not null)
            Core.Tabs.ZoomStore.Set(host, z);
    }

    private void SleepCheck()
    {
        var minutes = _settings.SleepMinutes;
        if (minutes <= 0 || _activeTabId is null)
            return;
        var now = DateTime.Now;
        foreach (var tab in _tabs.Tabs.ToList())
        {
            if (tab.IsPinned || tab.IsSleeping || tab.TabId == _activeTabId)
                continue;
            if ((now - tab.LastActivated).TotalMinutes >= minutes
                && _runtimes.TryGetValue(tab.TabId, out _))
            {
                _runtimeCoordinator.Sleep(tab.TabId);
                tab.IsSleeping = true;
            }
        }
    }

    private void WakeTab(Tab tab)
    {
        if (_runtimes.ContainsKey(tab.TabId))
            return;
        tab.IsSleeping = false;
        CreateRuntime(tab, tab.Url);
    }

    private Core.Tabs.Tab? TabItemAt(System.Windows.Point p)
    {
        var element = TabStrip.InputHitTest(p) as DependencyObject;
        while (element is not null && element is not System.Windows.Controls.ListBoxItem)
            element = System.Windows.Media.VisualTreeHelper.GetParent(element);
        return (element as System.Windows.Controls.ListBoxItem)?.DataContext as Core.Tabs.Tab;
    }

    private void TabStrip_ContextMenuOpening(object sender, System.Windows.Controls.ContextMenuEventArgs e)
    {
        if (TabItemAt(Mouse.GetPosition(TabStrip)) is not Core.Tabs.Tab tab)
            return;
        TabStrip.ContextMenu ??= new System.Windows.Controls.ContextMenu();
        var menu = TabStrip.ContextMenu;
        menu.Items.Clear();
        var close = new System.Windows.Controls.MenuItem { Header = "关闭标签" };
        close.Click += (_, _) => _tabs.CloseTab(tab.TabId);
        var closeOthers = new System.Windows.Controls.MenuItem { Header = "关闭其他标签" };
        closeOthers.Click += (_, _) => _tabs.CloseOthers(tab.TabId);
        var closeRight = new System.Windows.Controls.MenuItem { Header = "关闭右侧标签" };
        closeRight.Click += (_, _) => _tabs.CloseRight(tab.TabId);
        var pin = new System.Windows.Controls.MenuItem { Header = tab.IsPinned ? "取消固定标签" : "固定标签" };
        pin.Click += (_, _) => _tabs.SetPinned(tab.TabId, !tab.IsPinned);
        var dup = new System.Windows.Controls.MenuItem { Header = "复制标签" };
        dup.Click += (_, _) => _tabs.Duplicate(tab.TabId);
        var reopen = new System.Windows.Controls.MenuItem
        {
            Header = _tabs.ClosedCount > 0 ? "重新打开已关闭的标签" : "重新打开已关闭的标签（无）",
            IsEnabled = _tabs.ClosedCount > 0,
        };
        reopen.Click += (_, _) => ReopenClosedTab();
        menu.Items.Add(close);
        menu.Items.Add(closeOthers);
        menu.Items.Add(closeRight);
        menu.Items.Add(new System.Windows.Controls.Separator());
        menu.Items.Add(pin);
        menu.Items.Add(dup);
        menu.Items.Add(new System.Windows.Controls.Separator());
        menu.Items.Add(reopen);
    }

    private void ReopenClosedTab()
    {
        var s = _tabs.PopClosed();
        if (s is not null)
            _tabs.NewTab(s.Url, s.Title);
    }

    private void TabStrip_PreviewMouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Middle || e.ButtonState != MouseButtonState.Pressed)
            return;
        if (TabItemAt(e.GetPosition(TabStrip)) is Core.Tabs.Tab tab)
        {
            _tabs.CloseTab(tab.TabId);
            e.Handled = true;
        }
    }

    // —— 页内查找（逻辑在 FindBarController——上帝对象拆分第一批） ——
    private void FindBox_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(FindBox.Text))
            _ = _find.SearchAsync(FindBox.Text, backwards: false);
    }

    private async void Find_Executed(object sender, RoutedEventArgs e)
    {
        var backwards = (e.OriginalSource as System.Windows.Controls.Button)?.Tag as string == "b";
        await _find.SearchAsync(FindBox.Text, backwards);
    }

    private void CloseFind_Click(object sender, RoutedEventArgs e) => _find.Close();

    // —— 地址栏自动补全（逻辑在 SuggestionController） ——
    private void SuggestionList_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && _suggest.Selected() is { } sel)
        {
            _suggest.Pick(sel);
            e.Handled = true;
        }
        else if (e.Key == Key.Escape)
        {
            _suggest.Close();
            e.Handled = true;
        }
    }

    /// <summary>鼠标点击建议项即导航（此前仅键盘可达——鼠标点击只关弹层）。</summary>
    private void SuggestionList_PreviewMouseLeftButtonUp(object sender, MouseButtonEventArgs e)
    {
        if (_suggest.Selected() is { } sel)
        {
            _suggest.Pick(sel);
            e.Handled = true;
        }
    }

    // —— InPrivate ——
    private void InPrivate_Click(object sender, RoutedEventArgs e) => OpenInPrivateNew();

    private void OpenInPrivateNew() => new InPrivateWindow().Show();

    // —— 窗口状态记忆 ——
    private void SaveWindowState()
    {
        _settings.WindowMaximized = WindowState == WindowState.Maximized;
        if (WindowState == WindowState.Normal)
        {
            _settings.WindowLeft = Left;
            _settings.WindowTop = Top;
            _settings.WindowWidth = Width;
            _settings.WindowHeight = Height;
        }
    }
    private void RestoreWindowState()
    {
        var sw = SystemParameters.VirtualScreenWidth;
        var sh = SystemParameters.VirtualScreenHeight;
        Width = _settings.WindowWidth > 400 ? _settings.WindowWidth : 1200;
        Height = _settings.WindowHeight > 300 ? _settings.WindowHeight : 800;
        if (!double.IsNaN(_settings.WindowLeft) && !double.IsNaN(_settings.WindowTop)
            && _settings.WindowLeft < sw && _settings.WindowTop < sh)
        {
            Left = _settings.WindowLeft;
            Top = _settings.WindowTop;
        }
        if (_settings.WindowMaximized)
            WindowState = WindowState.Maximized;
    }

    // ================= 会话持久化 =================

    private void RestoreSessionOrStart()
    {
        var tabs = _sessionStore.Load(out var currentTabId);
        if (tabs.Count == 0)
        {
            _tabs.NewTab(HomeUrl);
            return;
        }
        RebuildTabsFromSnapshot(tabs, currentTabId);
    }

    /// <summary>会话快照 → 标签集合 + runtime 重建 + 激活（启动自动恢复与
    /// NTP 手动恢复共用——此前两份逐行复制漂移）。</summary>
    private void RebuildTabsFromSnapshot(IReadOnlyList<TabSessionStore.SessionTab> saved, string? currentTabId)
    {
        _tabs.SeedSession(
            saved.Select(t => (t.TabId, t.Url, t.Title, t.IsPinned)),
            currentTabId);
        foreach (var tab in _tabs.Tabs)
        {
            CreateRuntime(tab, tab.Url);
            _tabs.UpdateUrl(tab.TabId, tab.Url);
        }
        var active = _tabs.Current;
        if (active is not null)
            OnTabSwitched(active);
    }

    /// <summary>会话落盘（防抖）：每次导航完成/开关标签都只是标脏 + 重启 2s
    /// 计时——此前每次 NavigationCompleted 同步写 SQLite（每页加载两写：
    /// 历史一条 + 会话全量重写，长会话写放大）。窗口关闭/休眠前由
    /// FlushSession 强制刷盘兜底。</summary>
    private void SaveSession()
    {
        if (_restoring)
            return;  // 恢复流程中关闭旧标签不落盘——避免覆盖待恢复快照
        if (_sessionSaveTimer is null)
        {
            _sessionSaveTimer = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(SessionSaveDebounceMs),
            };
            _sessionSaveTimer.Tick += (_, _) =>
            {
                _sessionSaveTimer!.Stop();
                _sessionStore.Save(_tabs.Tabs, _tabs.CurrentTabId);
            };
        }
        _sessionSaveTimer.Stop();
        _sessionSaveTimer.Start();
    }

    /// <summary>立即落盘（窗口关闭/正常退出路径——防抖未到期的脏数据不丢）。</summary>
    private void FlushSession()
    {
        _sessionSaveTimer?.Stop();
        if (!_restoring)
            _sessionStore.Save(_tabs.Tabs, _tabs.CurrentTabId);
    }

    // ================= M3 会话恢复（新标签页手动入口） =================

    private bool _restoring;

    /// <summary>M3：手动恢复上次会话（NTP「恢复上次会话」按钮——重启后
    /// 重开上次页面集合；自动恢复仍由启动流程承担）。恢复期间抑制 SaveSession
    /// （关闭现有标签会触发落盘，否则会覆盖即将恢复的快照）。</summary>
    private void RestoreSavedSession()
    {
        var saved = _sessionStore.Load(out var currentTabId);
        if (saved.Count == 0)
        {
            ShowFeedback("没有可恢复的已保存会话", isWarning: true);
            return;
        }
        _restoring = true;
        try
        {
            foreach (var tab in _tabs.Tabs.ToList())
                _tabs.CloseTab(tab.TabId);
            RebuildTabsFromSnapshot(saved, currentTabId);
        }
        finally
        {
            _restoring = false;
        }
        SaveSession();
        ShowFeedback($"已恢复上次会话（{saved.Count} 个标签）");
    }

    // ================= 地址栏与导航 =================

    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        _suggest.OnTextChanged();
    }

    /// <summary>M1：地址栏获得焦点即全选（Ctrl+L 与鼠标点击同语义——
    /// 对齐 Python shell_toolbar 聚焦选中契约）。</summary>
    private void AddressBar_GotKeyboardFocus(object sender, KeyboardFocusChangedEventArgs e) =>
        AddressBar.SelectAll();

    private void SyncAddressBar(string url)
    {
        if (!AddressBar.IsKeyboardFocused)
            AddressBar.Text = url;
    }

    private void NavigateFromAddressBar()
    {
        // 输入归一单源（UrlNormalizer——与 Android SearchEngines.kt 跨端契约对齐）；
        // 最终仍经该标签 HostWebView 的 NavigationStarting → Broker 决策。
        var target = UrlNormalizer.Normalize(AddressBar.Text, _settings.SearchEngine);
        if (target is null)
        {
            ErrorPage.Text = "无法导航：输入为空，或属于非导航协议（file:/javascript:/data: 等已被拒绝）。";
            ErrorPagePanel.Visibility = Visibility.Visible;
            return;
        }
        // 归一器已保证产物可被 Uri 解析；此处兜底捕获非法输入（此前直接
        // new Uri(target)，"http://" 类输入抛 UriFormatException）
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var runtime))
        {
            if (!SafeNavigate(runtime, target))
            {
                ErrorPage.Text = "无法导航：地址无效。";
                ErrorPagePanel.Visibility = Visibility.Visible;
            }
        }
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (_suggest.IsOpenWithItems)
        {
            if (e.Key == Key.Down)
            {
                _suggest.MoveSelection(1);
                e.Handled = true; return;
            }
            if (e.Key == Key.Up)
            {
                _suggest.MoveSelection(-1);
                e.Handled = true; return;
            }
            if (e.Key == Key.Enter && _suggest.Selected() is { } sel)
            {
                _suggest.Pick(sel);
                e.Handled = true; return;
            }
            if (e.Key == Key.Escape)
            {
                _suggest.Close();
                e.Handled = true; return;
            }
        }
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }

    private void Open_Click(object sender, RoutedEventArgs e) => NavigateFromAddressBar();

    private Microsoft.Web.WebView2.Wpf.WebView2? ActiveControl() =>
        _activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r) ? r.Control : null;

    /// <summary>M2 收藏☆：toggle 当前页（零页面可控参数——URL/标题服务端取，
    /// 与 Android AegisBridge/Python toggle_bookmark 同安全模型）。</summary>
    private void Star_Click(object sender, RoutedEventArgs e)
    {
        var tab = _tabs.Current;
        if (tab is null || !Uri.TryCreate(tab.Url, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            ShowFeedback("当前页面不支持收藏", isWarning: true);
            return;
        }
        var wasStarred = _bookmarks.Contains(tab.Url);
        var ok = wasStarred
            ? _bookmarks.Remove(tab.Url)
            : _bookmarks.Add(string.IsNullOrWhiteSpace(tab.Title) ? uri.Host : tab.Title, tab.Url);
        ShowFeedback(ok ? (wasStarred ? "已取消收藏" : "已收藏") : "操作失败", isWarning: !ok);
    }

    private void Settings_Click(object sender, RoutedEventArgs e)
    {
        if (_settingsWindow is null || !_settingsWindow.IsLoaded)
        {
            _settingsWindow = new SettingsWindow(_settings, _broker, this, _settingsService) { Owner = this };
            // 创建即换肤——此前漏调：浅色模式下首次打开设置窗仍深色，直到下次
            // 全局换肤才纠正（对比历史/书签/下载三处创建时都有）
            _settingsWindow.ApplyTheme(_settings.Theme);
        }
        _settingsWindow.Show();
        _settingsWindow.Activate();
    }

    /// <summary>在当前激活标签导航到指定 URL（供书签管理器等调用）。</summary>
    public void OpenInActiveTab(string url)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var runtime))
            SafeNavigate(runtime, url);
    }

    private void BookmarkBarItem_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button { Tag: string url }
            && _activeTabId is not null
            && _runtimes.TryGetValue(_activeTabId, out var rt))
            SafeNavigate(rt, url);
    }

    private void BookmarkManager_Click(object sender, RoutedEventArgs e)
    {
        if (_bookmarkManagerWindow is null || !_bookmarkManagerWindow.IsLoaded)
        {
            _bookmarkManagerWindow = new BookmarkManagerWindow(_bookmarks, this) { Owner = this };
            _bookmarkManagerWindow.ApplyTheme(_settings.Theme);
        }
        _bookmarkManagerWindow.Show();
        _bookmarkManagerWindow.Activate();
    }

    private void History_Click(object sender, RoutedEventArgs e)
    {
        if (_historyWindow is null || !_historyWindow.IsLoaded)
        {
            _historyWindow = new HistoryWindow(_history) { Owner = this };
            _historyWindow.ApplyTheme(_settings.Theme);
        }
        _historyWindow.Show();
        _historyWindow.Activate();
    }

    /// <summary>M4 下载管理面板（共享数据源——新下载自动进入列表）。</summary>
    private void Downloads_Click(object sender, RoutedEventArgs e)
    {
        if (_downloadsWindow is null || !_downloadsWindow.IsLoaded)
        {
            _downloadsWindow = new DownloadsWindow(_downloads) { Owner = this };
            _downloadsWindow.ApplyTheme(_settings.Theme);
        }
        _downloadsWindow.Show();
        _downloadsWindow.Activate();
    }

    /// <summary>反馈条显示（2.5s 自动隐藏——不静默原则的轻量实现）。</summary>
    private void ShowFeedback(string message, bool isWarning = false)
    {
        FeedbackText.Text = message;
        FeedbackBar.Background = new System.Windows.Media.SolidColorBrush(
            isWarning ? System.Windows.Media.Color.FromArgb(0xFF, 0x2A, 0x12, 0x15)
                      : System.Windows.Media.Color.FromArgb(0xFF, 0x0F, 0x2A, 0x1B));
        FeedbackBar.Visibility = Visibility.Visible;
        // Tick 处理器只在首次创建时订阅一次（审计 M4：#Bug5 此前每次调用都
        // 追加一个新闭包且不摘除——长会话内事件累积成为驻留对象泄漏）
        if (_feedbackTimer is null)
        {
            _feedbackTimer = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(FeedbackHideMs),
            };
            _feedbackTimer.Tick += (_, _) =>
            {
                FeedbackBar.Visibility = Visibility.Collapsed;
                _feedbackTimer!.Stop();
            };
        }
        _feedbackTimer.Stop();
        _feedbackTimer.Start();
    }

    /// <summary>M3 源码查看器（Ctrl+U）：后台线程抓取当前页（15s/5MB 上限），
    /// 全转义纯文本展示于独立窗口——查看源码永不等于执行源码
    /// （Python api_bridge.view_source 语义移植）。</summary>
    private void OpenSourceViewer()
    {
        var tab = _tabs.Current;
        if (tab is null
            || !Uri.TryCreate(tab.Url, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            ShowFeedback("当前页面不支持查看源代码（仅限 http/https）", isWarning: true);
            return;
        }
        var url = tab.Url;
        ShowFeedback("正在获取页面源代码…");
        Task.Run(async () =>
        {
            try
            {
                using var http = new System.Net.Http.HttpClient
                {
                    Timeout = TimeSpan.FromSeconds(SourceFetchTimeoutSec),
                };
                http.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (AegisBrowser-SourceViewer)");
                using var response = await http.GetAsync(url);
                response.EnsureSuccessStatusCode();
                var bytes = await response.Content.ReadAsByteArrayAsync();
                if (bytes.Length > SourceMaxBytes)
                    throw new InvalidOperationException("源码超过 5MB 上限");
                var text = System.Text.Encoding.UTF8.GetString(bytes);
                Dispatcher.Invoke(() =>
                {
                    // 抓取期间主窗口可能已关闭——Owner=已关闭窗口会抛异常
                    if (!IsLoaded)
                        return;
                    var viewer = new SourceViewerWindow(url, text) { Owner = this };
                    viewer.ApplyTheme(_settings.Theme);
                    _sourceViewerWindows.RemoveAll(w => !w.IsLoaded);
                    _sourceViewerWindows.Add(viewer);
                    viewer.Show();
                    ShowFeedback("源码已加载（全转义，零脚本执行）");
                });
            }
            catch (Exception ex)
            {
                Dispatcher.Invoke(() =>
                    ShowFeedback($"获取源码失败：{ex.Message}", isWarning: true));
            }
        });
    }

    private void Back_Click(object sender, RoutedEventArgs e) => ActiveControl()?.GoBack();
    private void Forward_Click(object sender, RoutedEventArgs e) => ActiveControl()?.GoForward();
    private void Refresh_Click(object sender, RoutedEventArgs e) => ActiveControl()?.Reload();
    private void Stop_Click(object sender, RoutedEventArgs e) => ActiveControl()?.Stop();
    /// <summary>主页（Edge 对齐：回到新标签页，导航仍经 broker 决策）。</summary>
    private void Home_Click(object sender, RoutedEventArgs e)
    {
        if (ActiveRuntime() is { } runtime)
            SafeNavigate(runtime, HomeUrl);
    }

    /// <summary>个人资料占位：无账号体系，点击聚焦地址栏（对齐 Edge 圆钮位置）。</summary>
    private void Profile_Click(object sender, RoutedEventArgs e)
    {
        AddressBar.Focus();
        AddressBar.SelectAll();
    }

    // ================= M1 标签条拖拽排序（逻辑在 TabStripDragController） =================

    private void TabStrip_PreviewMouseMove(object sender, MouseEventArgs e) =>
        _tabDrag.HandlePreviewMouseMove(e);

    private void TabStrip_DragOver(object sender, DragEventArgs e) =>
        _tabDrag.HandleDragOver(e);

    private void TabStrip_Drop(object sender, DragEventArgs e) =>
        _tabDrag.HandleDrop(e);

    // ================= 导航确认面板（逻辑在 ApprovalPanelController） =================

    private void ApprovalAllow_Click(object sender, RoutedEventArgs e) => _approval.Allow();

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e) => _approval.Deny();

    private void ShowRejection(string message)
    {
        ErrorPage.Text = message;
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    // ================= 快捷键与关闭 =================

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // Ctrl+L 聚焦地址栏 / Ctrl+T 新建 / Ctrl+W 关闭当前（标签条 tooltip 契约）
        if (Keyboard.Modifiers == (ModifierKeys.Control | ModifierKeys.Shift))
        {
            if (e.Key == Key.Tab)
            {
                CycleTab(-1);
                e.Handled = true;
                return;
            }
            if (e.Key == Key.T)
            {
                ReopenClosedTab();
                e.Handled = true;
                return;
            }
        }
        else if (Keyboard.Modifiers == ModifierKeys.Control)
        {
            switch (e.Key)
            {
                case Key.L:
                    AddressBar.Focus();
                    AddressBar.SelectAll();
                    e.Handled = true;
                    return;
                case Key.T:
                    _tabs.NewTab(HomeUrl);
                    e.Handled = true;
                    return;
                case Key.W when _tabs.CurrentTabId is not null:
                    _tabs.CloseTab(_tabs.CurrentTabId);
                    e.Handled = true;
                    return;
                case Key.U:
                    OpenSourceViewer();
                    e.Handled = true;
                    return;
                case Key.F:
                    _find.Open();
                    e.Handled = true;
                    return;
                case Key.H:
                    History_Click(this, e);
                    e.Handled = true;
                    return;
                case Key.J:
                    Downloads_Click(this, e);
                    e.Handled = true;
                    return;
                case Key.D:
                    Star_Click(this, e);
                    e.Handled = true;
                    return;
                case Key.R:
                    ActiveControl()?.Reload();
                    e.Handled = true;
                    return;
                case Key.Tab:
                    CycleTab(1);
                    e.Handled = true;
                    return;
                case Key.D0:
                case Key.NumPad0:
                    ActiveRuntime()?.ResetZoom();
                    e.Handled = true;
                    return;
                case Key.OemPlus:
                case Key.Add:
                    ZoomActive(0.1);
                    e.Handled = true;
                    return;
                case Key.OemMinus:
                case Key.Subtract:
                    ZoomActive(-0.1);
                    e.Handled = true;
                    return;
                // Ctrl+1..8 直达标签 / Ctrl+9 末位标签（Edge 契约）
                case Key.D1 or Key.D2 or Key.D3 or Key.D4 or Key.D5
                     or Key.D6 or Key.D7 or Key.D8 or Key.D9
                     or Key.NumPad1 or Key.NumPad2 or Key.NumPad3 or Key.NumPad4 or Key.NumPad5
                     or Key.NumPad6 or Key.NumPad7 or Key.NumPad8 or Key.NumPad9:
                    JumpToTabByKey(e.Key);
                    e.Handled = true;
                    return;
            }
        }
        else if (Keyboard.Modifiers == ModifierKeys.Alt)
        {
            // Alt+←/→ 历史
            if (e.Key == Key.Left)
            {
                ActiveControl()?.GoBack();
                e.Handled = true;
                return;
            }
            if (e.Key == Key.Right)
            {
                ActiveControl()?.GoForward();
                e.Handled = true;
                return;
            }
        }
        else if (Keyboard.Modifiers == ModifierKeys.None)
        {
            switch (e.Key)
            {
                case Key.F5:
                    ActiveControl()?.Reload();
                    e.Handled = true;
                    return;
                case Key.F6:
                    AddressBar.Focus();
                    AddressBar.SelectAll();
                    e.Handled = true;
                    return;
                case Key.Tab:
                    // 无修饰 Tab 由 WPF 焦点遍历处理（地址栏/查找框间移动）
                    break;
            }
        }
        if (!_approval.IsVisible || e.Key != Key.Escape)
            return;
        _approval.Deny();
        e.Handled = true;
    }

    /// <summary>Ctrl+Tab / Ctrl+Shift+Tab 循环切换标签。</summary>
    private void CycleTab(int direction)
    {
        var count = _tabs.Tabs.Count;
        if (count == 0)
            return;
        var current = _tabs.CurrentTabId is { } id ? _tabs.Tabs.ToList().FindIndex(t => t.TabId == id) : 0;
        var next = ((current < 0 ? 0 : current) + direction + count) % count;
        _tabs.SwitchTo(_tabs.Tabs[next].TabId);
    }

    /// <summary>Ctrl+1..8 直达对应标签，Ctrl+9 末位标签。</summary>
    private void JumpToTabByKey(Key key)
    {
        var digit = key switch
        {
            Key.D1 => 1, Key.D2 => 2, Key.D3 => 3, Key.D4 => 4, Key.D5 => 5,
            Key.D6 => 6, Key.D7 => 7, Key.D8 => 8, Key.D9 => 9,
            Key.NumPad1 => 1, Key.NumPad2 => 2, Key.NumPad3 => 3, Key.NumPad4 => 4,
            Key.NumPad5 => 5, Key.NumPad6 => 6, Key.NumPad7 => 7, Key.NumPad8 => 8,
            Key.NumPad9 => 9,
            _ => 0,
        };
        if (digit == 0)
            return;
        var index = digit == 9 ? _tabs.Tabs.Count - 1 : digit - 1;
        if (index >= 0 && index < _tabs.Tabs.Count)
            _tabs.SwitchTo(_tabs.Tabs[index].TabId);
    }

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        FlushSession();
        SaveWindowState();
        _settings.ZoomByHost = ZoomStore.Snapshot();
        _settingsService.Apply(_settings);
        foreach (var runtime in _runtimes.Values)
            runtime.Host.RejectPendingNavigation();
    }

    private void SetNavigationControlsEnabled(bool isEnabled)
    {
        AddressBar.IsEnabled = isEnabled;
        OpenButton.IsEnabled = isEnabled;
        BackButton.IsEnabled = isEnabled;
        ForwardButton.IsEnabled = isEnabled;
        RefreshButton.IsEnabled = isEnabled;
        StopButton.IsEnabled = isEnabled;
        HomeButton.IsEnabled = isEnabled;
    }

    protected override void OnClosed(EventArgs e)
    {
        FlushSession();
        // 审计修复：停全部定时器 + 解绑事件——主窗口关闭但 InPrivate 存活时，
        // 此前 30s 睡眠巡检/建议定时器继续空转、ZoomStore.Changed 永久持有
        // 对已关窗口的引用（内存泄漏）
        _sleepTimer?.Stop();
        _suggest.StopDebounce();
        _feedbackTimer?.Stop();
        if (_zoomChangedHandler is not null)
            ZoomStore.Changed -= _zoomChangedHandler;
        _tabs.TabOpened -= OnTabOpened;
        _tabs.TabClosed -= OnTabClosed;
        _tabs.TabSwitched -= OnTabSwitched;
        _runtimeCoordinator.NtpNavigationFailed -= OnNtpNavigationFailed;
        // 全部 runtime 经协调器统一销毁（先摘视觉树再释放，令牌一并取消）
        _runtimeCoordinator.Dispose();
        _runtimes.Clear();
        _broker.Dispose();
        base.OnClosed(e);
    }
}

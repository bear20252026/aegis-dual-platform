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
    private readonly BrowserPolicyBroker _broker = new();
    private readonly TabManager _tabs = new();
    private readonly Dictionary<string, TabRuntime> _runtimes = new();
    private readonly TabSessionStore _sessionStore = new(AppPaths.SessionDbPath);
    private string? _activeTabId;
    private string? _pendingConfirmTabId;
    private bool _suppressTabSelection;
    private readonly BookmarkStore _bookmarks =
        new(Path.Combine(AppPaths.DataDir, "bookmarks.db"));
    private readonly HistoryStore _history =
        new(Path.Combine(AppPaths.DataDir, "history.db"));
    private readonly AppSettings _settings =
        AppSettings.Load(AppSettings.DefaultPath);
    private HistoryWindow? _historyWindow;
    private SettingsWindow? _settingsWindow;
    private DownloadsWindow? _downloadsWindow;
    private System.Windows.Threading.DispatcherTimer? _feedbackTimer;
    // M4 下载管理面板数据源（跨标签共享——DownloadItem 由 TabRuntime 下载事件注入）
    private readonly System.Collections.ObjectModel.ObservableCollection<Core.Downloads.DownloadItem> _downloads = new();

    private const string HomeUrl = Chrome.Ntp.NtpAssets.Url;

    public MainWindow()
    {
        InitializeComponent();
        ApplyTheme(_settings.Theme);
        _tabs.TabOpened += OnTabOpened;
        _tabs.TabClosed += OnTabClosed;
        _tabs.TabSwitched += OnTabSwitched;
        TabStrip.ItemsSource = _tabs.Tabs;
        RestoreSessionOrStart();
        StartThreatFeedRefresh();
        InitEngineCombo();
    }

    /// <summary>M2：搜索引擎下拉（AppSettings 持久化——重启动保持偏好）。</summary>
    private void InitEngineCombo()
    {
        EngineCombo.ItemsSource = UrlNormalizer.EngineUrls.Keys.ToList();
        EngineCombo.SelectedValue = _settings.SearchEngine;
    }

    // ================= 深/浅主题（对齐 Edge 明暗外观） =================

    /// <summary>按设置应用浏览器 chrome 主题（dark/light——九块 DynamicResource
    /// 色刷运行时替换，工具栏/标签/地址栏即时切换；其余独立窗口暂保持深色）。</summary>
    public void ApplyTheme(string? theme)
    {
        var light = string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        SetBrush("ChromeBackgroundBrush", light ? "#FFF5F5F7" : "#FF101827");
        SetBrush("ButtonOverlayBrush", light ? "#14000000" : "#33FFFFFF");
        SetBrush("ButtonOverlayHoverBrush", light ? "#20000000" : "#4DFFFFFF");
        SetBrush("ButtonOverlayPressedBrush", light ? "#2E000000" : "#66FFFFFF");
        SetBrush("FieldBackgroundBrush", light ? "#FFFFFFFF" : "#1FFFFFFF");
        SetBrush("FieldBorderBrush", light ? "#FFDADCE0" : "#2EFFFFFF");
        SetBrush("FieldBorderFocusedBrush", light ? "#FF0B57D0" : "#66FFFFFF");
        SetBrush("TextPrimaryBrush", light ? "#FF1A1A1A" : "#FFFFFFFF");
        SetBrush("TextSecondaryBrush", light ? "#FF5F6368" : "#B3FFFFFF");
        Background = light
            ? new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0xF5, 0xF5, 0xF7))
            : new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0x10, 0x18, 0x27));
    }

    private void SetBrush(string key, string hex)
    {
        if (System.Windows.Media.ColorConverter.ConvertFromString(hex) is System.Windows.Media.Color color)
            Resources[key] = new System.Windows.Media.SolidColorBrush(color);
    }

    private void Engine_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (EngineCombo.SelectedValue is not string engine)
            return;
        _settings.SearchEngine = engine;
        _settings.Save(AppSettings.DefaultPath);
    }

    /// <summary>M1-T2：威胁黑名单启动快照 + 订阅源后台刷新（对齐 Python 批次 2-1）。
    /// 订阅源经环境变量 AEGIS_THREAT_FEED_URL 配置（M4 移入设置界面）。</summary>
    private void StartThreatFeedRefresh()
    {
        var cachePath = Path.Combine(AppPaths.DataDir, "threat_feed.txt");
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
        Core.Security.SecurityLog.Write($"[tab] 创建标签 {tab.TabId} url={initialUrl}");
        var runtime = new TabRuntime(_broker, tab, initialUrl);
        _runtimes[tab.TabId] = runtime;
        runtime.Control.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
            {
                Core.Security.SecurityLog.Write(
                    $"[init] 标签 {tab.TabId} 初始化失败: {e.InitializationException?.Message ?? "e.IsSuccess=false（未知原因）"}");
                return;
            }
            var core = runtime.Control.CoreWebView2;
            BindVirtualHosts(core);
            runtime.OnCoreReady(core);
            // 虚拟主机地址（NTP/画板）：映射就绪后才导航，且**推迟到下一
            // Dispatcher 周期**——同一调用栈里 SetVirtualHostNameToFolderMapping
            // 后立即导航会因映射尚未传播到渲染进程而 ConnectionAborted
            //（实机复现：点主页能渲染、初始化时同步导航即 abort）。推迟后
            // 与「点主页成功」路径一致。
            if (Chrome.Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
            {
                var targetUrl = tab.Url;
                Dispatcher.BeginInvoke(() =>
                {
                    // 若该标签在延迟导航前已被关闭（销毁），直接跳过设置——否则
                    // 在已释放控件上设 Source 会抛异常，导致「新建标签删不掉」。
                    if (_runtimes.TryGetValue(tab.TabId, out var current) && ReferenceEquals(current, runtime))
                        runtime.Control.Source = new Uri(targetUrl);
                });
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
                if (!IsTopLevelNtpDocument(core))
                    return;
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
        runtime.Host.NavigationConfirmationRequested += (_, e) =>
        {
            _pendingConfirmTabId = tab.TabId;
            ShowConfirmation(e);
        };
        runtime.Host.NavigationConfirmationResolved += (_, _) => HideConfirmation();
        // target=_blank / window.open 链接：不再静默丢弃，改为验证公网地址后
        // 在当前窗口新建标签打开（对齐主流浏览器）。非法协议/内网/环回/保留
        // 地址一律拒绝（安全约束）。
        runtime.NewWindowRequested += targetUrl =>
        {
            if (!Core.UrlSafety.IsPublicHttpUrl(targetUrl))
            {
                ShowFeedback("已拒绝打开该链接（非公网地址）", isWarning: true);
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
        WebViewHost.Children.Add(runtime.Control);
    }

    /// <summary>M3：虚拟主机资源映射（start.html 单源 + 可选 GeoGebra 随包）。
    /// 只映射发布输出目录内容——不暴露任意文件系统路径。映射结果写入安全
    /// 日志——NTP 加载失败时可据此区分「资源根缺失」与「映射未生效」。</summary>
    private void BindVirtualHosts(CoreWebView2 core)
    {
        var ntpRoot = Chrome.Ntp.NtpAssets.ResolveContentRoot();
        Core.Security.SecurityLog.Write(
            $"[init] ntp 资源根 = {ntpRoot ?? "<null>"}（BaseDirectory={AppContext.BaseDirectory}）");
        if (ntpRoot is not null)
        {
            core.SetVirtualHostNameToFolderMapping(
                Chrome.Ntp.NtpAssets.HostName, ntpRoot,
                CoreWebView2HostResourceAccessKind.Allow);
            Core.Security.SecurityLog.Write(
                $"[init] {Chrome.Ntp.NtpAssets.HostName} 已映射 -> {ntpRoot}");
        }
        var geoRoot = Chrome.Ntp.NtpAssets.ResolveGeoRoot();
        if (geoRoot is not null)
        {
            core.SetVirtualHostNameToFolderMapping(
                Chrome.Ntp.NtpAssets.GeoHostName, geoRoot,
                CoreWebView2HostResourceAccessKind.Allow);
            Core.Security.SecurityLog.Write(
                $"[init] {Chrome.Ntp.NtpAssets.GeoHostName} 已映射 -> {geoRoot}");
        }
    }

    /// <summary>M3：新标签页宿主桥的顶层文档门禁——core.Source 为当前顶层
    /// 文档（非任一 iframe）。远程顶层页面即使内嵌 ntp.aegis.local 帧，顶层
    /// 来源仍为远程 host → 拒绝；从根上封死「帧内嵌复用受信桥」的绕过面。</summary>
    private static bool IsTopLevelNtpDocument(CoreWebView2 core) =>
        Uri.TryCreate(core.Source, UriKind.Absolute, out var uri)
        && uri.Host.Equals(Chrome.Ntp.NtpAssets.HostName, StringComparison.OrdinalIgnoreCase);

    /// <summary>M3：新标签页宿主桥服务组装（每标签一份——navigate/goBack/openGeo
    /// 作用于该标签自己的 WebView；数据服务共享单源）。</summary>
    private Chrome.Ntp.NtpBridge CreateNtpBridge(TabRuntime runtime)
    {
        return new Chrome.Ntp.NtpBridge(new Chrome.Ntp.NtpBridge.Services(
            SearchEngine: () => _settings.SearchEngine,
            SetSearchEngine: engine =>
            {
                _settings.SearchEngine = engine;
                _settings.Save(AppSettings.DefaultPath);
                EngineCombo.SelectedValue = engine;
            },
            Wallpaper: () => string.IsNullOrWhiteSpace(_settings.NtpWallpaper)
                ? Chrome.Ntp.NtpAssets.DefaultWallpaper
                : _settings.NtpWallpaper,
            SetWallpaper: name =>
            {
                _settings.NtpWallpaper = name;
                _settings.Save(AppSettings.DefaultPath);
            },
            Bookmarks: () => _bookmarks.All(),
            SavedSessionCount: () => _sessionStore.Load().Count,
            RestoreSession: RestoreSavedSession,
            Navigate: target =>
            {
                // 桥已归一（非导航协议 fail-closed）——此处直接进入
                // NavigationStarting→broker 唯一授权路径
                runtime.Control.Source = new Uri(target!);
            },
            GoBack: () =>
            {
                if (runtime.Control.CanGoBack)
                {
                    runtime.Control.GoBack();
                    return true;
                }
                return false;
            },
            OpenGeo: () =>
            {
                if (Chrome.Ntp.NtpAssets.ResolveGeoRoot() is null)
                    return false;  // 资源未随包——fail-closed 降级（按钮置灰）
                runtime.Control.Source = new Uri(
                    $"https://{Chrome.Ntp.NtpAssets.GeoHostName}/{Chrome.Ntp.NtpAssets.GeoEntryPath}");
                return true;
            },
            ImportSources: () =>
            {
                // 探测 = 仅文件存在性检查（不读取内容）；书签/历史能力按来源汇总
                var byBrowser = new Dictionary<string, (bool Bookmarks, bool History)>();
                foreach (var source in BookmarkImporter.DetectSources())
                    byBrowser[source.Browser] = (true, false);
                foreach (var source in Core.History.HistoryImporter.DetectSources())
                    byBrowser[source.Browser] = byBrowser.TryGetValue(source.Browser, out var known)
                        ? (known.Bookmarks, true)
                        : (false, true);
                var sources = new List<Chrome.Ntp.NtpBridge.ImportSourceSnapshot>();
                foreach (var pair in byBrowser)
                    sources.Add(new(pair.Key, pair.Value.Bookmarks, pair.Value.History));
                return sources;
            },
            ImportBookmarks: sourceFilter =>
            {
                var imported = 0;
                var total = 0;
                var results = new List<Chrome.Ntp.NtpBridge.ImportResult>();
                foreach (var source in FilterSources(BookmarkImporter.DetectSources(), sourceFilter, s => s.Browser))
                {
                    try
                    {
                        var candidates = BookmarkImporter.Parse(source.Path);
                        var (one, all) = BookmarkImporter.ImportTo(_bookmarks, candidates);
                        results.Add(new(source.Browser, one, all));
                        imported += one;
                        total += all;
                    }
                    catch (Exception)
                    {
                        // 单来源失败不阻断其余来源（可选功能——对齐 Python 口径）
                    }
                }
                return (imported, total, results);
            },
            ImportHistory: (limit, sourceFilter) =>
            {
                var imported = 0;
                var total = 0;
                var results = new List<Chrome.Ntp.NtpBridge.ImportResult>();
                foreach (var source in FilterSources(Core.History.HistoryImporter.DetectSources(), sourceFilter, s => s.Browser))
                {
                    try
                    {
                        var candidates = Core.History.HistoryImporter.Parse(source.Path, limit);
                        var (one, all) = Core.History.HistoryImporter.ImportTo(_history, candidates);
                        results.Add(new(source.Browser, one, all));
                        imported += one;
                        total += all;
                    }
                    catch (Exception)
                    {
                        // 单来源失败不阻断其余来源（可选功能——对齐 Python 口径）
                    }
                }
                return (imported, total, results);
            }));
    }

    /// <summary>导入来源过滤（空/all = 全部来源；否则仅指定浏览器）。</summary>
    private static IEnumerable<T> FilterSources<T>(
        IReadOnlyList<T> sources, string? browserFilter, Func<T, string> browserOf)
    {
        if (string.IsNullOrEmpty(browserFilter) || browserFilter == "all")
        {
            foreach (var source in sources)
                yield return source;
            yield break;
        }
        foreach (var source in sources)
        {
            if (browserOf(source) == browserFilter)
                yield return source;
        }
    }

    private void OnTabClosed(string tabId)
    {
        if (_runtimes.Remove(tabId, out var runtime))
        {
            // 安全顺序（Android P2-9 教训）：先摘视觉树再 dispose
            WebViewHost.Children.Remove(runtime.Control);
            try
            {
                runtime.Dispose();
            }
            catch (Exception ex)
            {
                // 个别 WebView 未完全初始化的 Dispose 可能抛——标签集合已移除、
                // 视觉树已摘除，关闭成功；此处容错不阻断
                Core.Security.SecurityLog.Write($"[tab] 标签 {tabId} 销毁容错: {ex.GetType().Name}: {ex.Message}");
            }
        }
        SaveSession();
    }

    private void OnTabSwitched(Tab tab)
    {
        _activeTabId = tab.TabId;
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
        _tabDragStart = e.GetPosition(TabStrip);
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

    // ================= 会话持久化 =================

    private void RestoreSessionOrStart()
    {
        var tabs = _sessionStore.Load(out var currentTabId);
        if (tabs.Count == 0)
        {
            _tabs.NewTab(HomeUrl);
            return;
        }
        _tabs.SeedSession(
            tabs.Select(t => (t.TabId, t.Url, t.Title)),
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

    private void SaveSession()
    {
        if (_restoring)
            return;  // 恢复流程中关闭旧标签不落盘——避免覆盖待恢复快照
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
            _tabs.SeedSession(
                saved.Select(t => (t.TabId, t.Url, t.Title)),
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
        finally
        {
            _restoring = false;
        }
        SaveSession();
        ShowFeedback($"已恢复上次会话（{saved.Count} 个标签）");
    }

    // ================= 地址栏与导航 =================

    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e) =>
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;

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
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var runtime))
            runtime.Control.Source = new Uri(target);
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
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
            _settingsWindow = new SettingsWindow(_settings, _broker, this) { Owner = this };
        }
        _settingsWindow.Show();
        _settingsWindow.Activate();
    }

    private void History_Click(object sender, RoutedEventArgs e)
    {
        if (_historyWindow is null || !_historyWindow.IsLoaded)
        {
            _historyWindow = new HistoryWindow(_history);
            _historyWindow.Owner = this;
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
                Interval = TimeSpan.FromSeconds(2.5),
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
                    Timeout = TimeSpan.FromSeconds(15),
                };
                http.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (AegisBrowser-SourceViewer)");
                using var response = await http.GetAsync(url);
                response.EnsureSuccessStatusCode();
                var bytes = await response.Content.ReadAsByteArrayAsync();
                if (bytes.Length > 5 * 1024 * 1024)
                    throw new InvalidOperationException("源码超过 5MB 上限");
                var text = System.Text.Encoding.UTF8.GetString(bytes);
                Dispatcher.Invoke(() =>
                {
                    new SourceViewerWindow(url, text) { Owner = this }.Show();
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
        if (ActiveControl() is { } control)
            control.Source = new Uri(HomeUrl);
    }

    /// <summary>个人资料占位：无账号体系，点击聚焦地址栏（对齐 Edge 圆钮位置）。</summary>
    private void Profile_Click(object sender, RoutedEventArgs e)
    {
        AddressBar.Focus();
        AddressBar.SelectAll();
    }

    // ================= M1 标签条拖拽排序 =================

    private System.Windows.Point _tabDragStart;

    private void TabStrip_PreviewMouseMove(object sender, MouseEventArgs e)
    {
        if (e.LeftButton != MouseButtonState.Pressed)
            return;
        var pos = e.GetPosition(TabStrip);
        // 真实移动超过系统最小拖拽阈值才进入拖拽——否则点按 ✕ 时的微小抖动
        // 会误触发拖拽、吞掉关闭点击（「标签只能新增不能删除」的根因）
        if (Math.Abs(pos.X - _tabDragStart.X) < SystemParameters.MinimumHorizontalDragDistance
            && Math.Abs(pos.Y - _tabDragStart.Y) < SystemParameters.MinimumVerticalDragDistance)
            return;
        if (IsOverCloseButton(pos))
            return;  // 关闭按钮区域不拖拽——交由其 Click 处理
        if (TabItemIndexUnderMouse(pos) is not int fromIndex)
            return;
        _tabDragStart = pos;  // 抑制重复 DoDragDrop
        // 容器级拖放（数据=来源索引）；DragOver/Drop 完成重排
        DragDrop.DoDragDrop(TabStrip, fromIndex, DragDropEffects.Move);
    }

    /// <summary>命中点是否落在某标签的关闭（✕）按钮上。</summary>
    private bool IsOverCloseButton(System.Windows.Point position)
    {
        if (TabStrip.InputHitTest(position) is not DependencyObject hit)
            return false;
        var probe = hit;
        while (probe is not null)
        {
            if (probe is System.Windows.Controls.Button button && button.Tag is string)
                return true;
            probe = System.Windows.Media.VisualTreeHelper.GetParent(probe);
        }
        return false;
    }

    private void TabStrip_DragOver(object sender, DragEventArgs e)
    {
        e.Effects = TabItemIndexUnderMouse(e.GetPosition(TabStrip)) is int
                    && e.Data.GetDataPresent(typeof(int))
            ? DragDropEffects.Move
            : DragDropEffects.None;
        e.Handled = true;
    }

    private void TabStrip_Drop(object sender, DragEventArgs e)
    {
        if (!e.Data.GetDataPresent(typeof(int))
            || TabItemIndexUnderMouse(e.GetPosition(TabStrip)) is not int toIndex)
            return;
        var fromIndex = (int)e.Data.GetData(typeof(int));
        // drop 落点为标签中心右侧时插入其后（末位拖动体验）
        if (toIndex > fromIndex && TabItemCenterIsBefore(e.GetPosition(TabStrip), toIndex))
            toIndex--;
        _tabs.MoveTab(Math.Min(fromIndex, _tabs.Tabs.Count - 1), Math.Max(0, toIndex));
        e.Handled = true;
    }

    /// <summary>标签条坐标下的标签索引（ListBox 容器命中——非标签区域返回 null）。</summary>
    private int? TabItemIndexUnderMouse(System.Windows.Point position)
    {
        var element = TabStrip.InputHitTest(position) as System.Windows.DependencyObject;
        while (element is not null && element is not System.Windows.Controls.ListBoxItem)
            element = System.Windows.Media.VisualTreeHelper.GetParent(element);
        return element is System.Windows.Controls.ListBoxItem item
            && TabStrip.ItemContainerGenerator.IndexFromContainer(item) is var idx && idx >= 0
            ? idx
            : null;
    }

    private bool TabItemCenterIsBefore(System.Windows.Point tabStripPosition, int index)
    {
        if (TabStrip.ItemContainerGenerator.ContainerFromIndex(index) is not System.Windows.Controls.ListBoxItem item)
            return false;
        var point = tabStripPosition - item.TranslatePoint(default, TabStrip);
        return point.X > item.ActualWidth / 2;
    }

    // ================= 导航确认面板（转发到发起标签的 HostWebView） =================

    private void ShowConfirmation(WebView.NavigationConfirmationRequestedEventArgs e)
    {
        ApprovalOrigin.Text = e.Request.Origin;
        ApprovalPath.Text = e.Request.Path;
        ApprovalScope.Text = e.Request.Scope;
        ApprovalExpiry.Text = $"此请求将在 {e.Request.ExpiresAt.ToLocalTime():yyyy-MM-dd HH:mm:ss} 过期。";
        SetNavigationControlsEnabled(false);
        ApprovalOverlay.Visibility = Visibility.Visible;
        Keyboard.Focus(ApprovalDenyButton);
    }

    private void HideConfirmation()
    {
        ApprovalOverlay.Visibility = Visibility.Collapsed;
        SetNavigationControlsEnabled(true);
        ApprovalOrigin.Text = string.Empty;
        ApprovalPath.Text = string.Empty;
        ApprovalScope.Text = string.Empty;
        ApprovalExpiry.Text = string.Empty;
        _pendingConfirmTabId = null;
    }

    private void ApprovalAllow_Click(object sender, RoutedEventArgs e)
    {
        if (_pendingConfirmTabId is null || !_runtimes.TryGetValue(_pendingConfirmTabId, out var runtime)
            || runtime.Control.CoreWebView2 is null)
        {
            _runtimes.TryGetValue(_pendingConfirmTabId ?? string.Empty, out var orphan);
            orphan?.Host.RejectPendingNavigation();
            ShowRejection("确认请求已失效、被拒绝或无法安全恢复导航。");
            return;
        }
        if (!runtime.Host.ApprovePendingNavigation(runtime.Control.CoreWebView2))
            ShowRejection("确认请求已失效、被拒绝或无法安全恢复导航。");
    }

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e)
    {
        if (_pendingConfirmTabId is not null && _runtimes.TryGetValue(_pendingConfirmTabId, out var runtime))
            runtime.Host.RejectPendingNavigation();
        ShowRejection("已拒绝该导航请求。");
    }

    private void ShowRejection(string message)
    {
        ErrorPage.Text = message;
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    // ================= 快捷键与关闭 =================

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // Ctrl+L 聚焦地址栏 / Ctrl+T 新建 / Ctrl+W 关闭当前（标签条 tooltip 契约）
        if (Keyboard.Modifiers == ModifierKeys.Control)
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
            }
        }
        if (ApprovalOverlay.Visibility != Visibility.Visible || e.Key != Key.Escape)
            return;
        if (_pendingConfirmTabId is not null && _runtimes.TryGetValue(_pendingConfirmTabId, out var runtime))
            runtime.Host.RejectPendingNavigation();
        ShowRejection("已拒绝该导航请求。");
        e.Handled = true;
    }

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        SaveSession();
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
        SaveSession();
        foreach (var runtime in _runtimes.Values)
        {
            WebViewHost.Children.Remove(runtime.Control);
            runtime.Dispose();
        }
        _runtimes.Clear();
        _broker.Dispose();
        base.OnClosed(e);
    }
}

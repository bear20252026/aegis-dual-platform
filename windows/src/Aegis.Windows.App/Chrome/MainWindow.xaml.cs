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
        var runtime = new TabRuntime(_broker, tab, initialUrl);
        _runtimes[tab.TabId] = runtime;
        runtime.Control.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
                return;
            var core = runtime.Control.CoreWebView2;
            BindVirtualHosts(core);
            runtime.OnCoreReady(core);
            // M3 新标签页宿主桥：仅 ntp.aegis.local 来源可达（远程页 per-origin
            // 关闭 WebMessage + 本桥双重校验）；导航意图回归 NavigationStarting→
            // broker 唯一授权路径
            var ntp = CreateNtpBridge(runtime);
            core.WebMessageReceived += (_, ev) => ntp.TryHandle(
                ev.Source, ev.WebMessageAsJson,
                result => core.PostWebMessageAsJson(
                    System.Text.Json.JsonSerializer.Serialize(result)));
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
        WebViewHost.Children.Add(runtime.Control);
    }

    /// <summary>M3：虚拟主机资源映射（start.html 单源 + 可选 GeoGebra 随包）。
    /// 只映射发布输出目录内容——不暴露任意文件系统路径。</summary>
    private void BindVirtualHosts(CoreWebView2 core)
    {
        var ntpRoot = Chrome.Ntp.NtpAssets.ResolveContentRoot();
        if (ntpRoot is not null)
        {
            core.SetVirtualHostNameToFolderMapping(
                Chrome.Ntp.NtpAssets.HostName, ntpRoot,
                CoreWebView2HostResourceAccessKind.Allow);
        }
        var geoRoot = Chrome.Ntp.NtpAssets.ResolveGeoRoot();
        if (geoRoot is not null)
        {
            core.SetVirtualHostNameToFolderMapping(
                Chrome.Ntp.NtpAssets.GeoHostName, geoRoot,
                CoreWebView2HostResourceAccessKind.Allow);
        }
    }

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
            runtime.Dispose();
        }
        SaveSession();
    }

    private void OnTabSwitched(Tab tab)
    {
        _activeTabId = tab.TabId;
        foreach (var pair in _runtimes)
            pair.Value.Control.Visibility = pair.Key == _activeTabId
                ? Visibility.Visible
                : Visibility.Collapsed;
        SyncAddressBar(tab.Url);
        _suppressTabSelection = true;
        TabStrip.SelectedItem = tab;
        _suppressTabSelection = false;
    }

    private void OnTabNavigationCompleted(string tabId, bool isSuccess, CoreWebView2WebErrorStatus status)
    {
        var tab = _tabs.Tabs.Count > 0 && tabId == _activeTabId ? _tabs.Current : null;
        if (tab is null)
            return;
        if (!isSuccess && status != CoreWebView2WebErrorStatus.OperationCanceled)
        {
            ErrorPage.Text = $"导航失败：{status}（已拒绝/无法加载）";
            ErrorPagePanel.Visibility = Visibility.Visible;
        }
        else
        {
            ErrorPagePanel.Visibility = Visibility.Collapsed;
        }
        if (tabId == _activeTabId)
            LoadingBar.Visibility = Visibility.Collapsed;
        SyncAddressBar(tab.Url);
        // 每次导航完成即落盘（对齐 Python 栈崩溃恢复能力——强杀/崩溃后
        // 重启仍可恢复到最后的页面集合，而非仅正常关闭时的快照）
        SaveSession();
    }

    // ================= 标签条交互 =================

    private void NewTab_Click(object sender, RoutedEventArgs e) => _tabs.NewTab(HomeUrl);

    private void TabClose_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as System.Windows.Controls.Button)?.Tag is string tabId)
            _tabs.CloseTab(tabId);
    }

    private void TabStrip_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressTabSelection)
            return;
        if (TabStrip.SelectedItem is Core.Tabs.Tab tab)
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
        var ok = _bookmarks.Contains(tab.Url)
            ? _bookmarks.Remove(tab.Url)
            : _bookmarks.Add(string.IsNullOrWhiteSpace(tab.Title) ? uri.Host : tab.Title, tab.Url);
        ShowFeedback(ok ? (ok ? "已收藏" : "操作失败") : "已取消收藏", isWarning: !ok);
        if (!ok)
            ShowFeedback("操作失败", isWarning: true);
    }

    private void Settings_Click(object sender, RoutedEventArgs e)
    {
        if (_settingsWindow is null || !_settingsWindow.IsLoaded)
        {
            _settingsWindow = new SettingsWindow(_settings, _broker) { Owner = this };
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
        _feedbackTimer ??= new System.Windows.Threading.DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(2.5),
        };
        _feedbackTimer.Tick += (_, _) =>
        {
            FeedbackBar.Visibility = Visibility.Collapsed;
            _feedbackTimer.Stop();
        };
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
    /// <summary>M1 主页：回到新标签页（导航仍经 broker 决策）。</summary>
    private void Home_Click(object sender, RoutedEventArgs e)
    {
        if (ActiveControl() is { } control)
            control.Source = new Uri(HomeUrl);
    }

    // ================= M1 标签条拖拽排序 =================

    private void TabStrip_PreviewMouseMove(object sender, MouseEventArgs e)
    {
        if (e.LeftButton != MouseButtonState.Pressed)
            return;
        if (TabItemIndexUnderMouse(e.GetPosition(TabStrip)) is not int fromIndex)
            return;
        // 容器级拖放（数据=来源索引）；DragOver/Drop 完成重排
        DragDrop.DoDragDrop(TabStrip, fromIndex, DragDropEffects.Move);
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

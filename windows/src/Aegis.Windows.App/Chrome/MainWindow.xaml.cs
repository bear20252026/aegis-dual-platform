namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
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
/// 控件（与页面 DOM 隔离——注入式 UI 成为历史）。
/// CS-377（2026-10-02 审计）：单文件 1424 行超「改造后 ≤500」红线——按职责
/// 拆 partial 文件（零行为变化、纯代码移动）：本文件=核心装配（字段/构造/
/// 主题/引擎/会话持久化/反馈条），Tabs=标签生命周期与交互，Shortcuts=快捷键
/// 与地址栏，SourceViewer=源码查看器，WindowState=窗口状态与关闭链，
/// Menus=右键菜单与工具栏入口。</summary>
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
        // CS-344（2026-10-01 审计）：DownloadRecordStore 移除——其注释承诺
        // "重启后仍可查看"，但 All() 零生产调用（DownloadItem 需持有原生
        // DownloadOperation，重启后无法重建），带 token 的 URL 无收益常驻磁盘
        private System.Windows.Threading.DispatcherTimer? _sleepTimer;
    // 会话落盘防抖（写放大治理）已外移 SessionSaveScheduler——可测的标脏/刷盘/恢复抑制
    private readonly SessionSaveScheduler _sessionSaver;
    private FindBarController _find = null!;
    private SuggestionController _suggest = null!;
    private Ntp.NtpBridgeFactory _ntpBridgeFactory = null!;
    private Action? _zoomChangedHandler;
    // CS-299：后台历史写入链尾——串行化保证先后序（详见 OnTabNavigationCompleted）
    private Task _historyWriteTail = Task.CompletedTask;
    // CS-355（2026-10-01 审计）：最近一次策略拒绝的用户可读原因（供
    // NavigationCompleted 的 OperationCanceled 分支呈现）
    // CS-386（2026-10-02 审计）：窗口级单槽改按 tabId 存取——此前任一标签的
    // 拒绝都可能被另一标签的 NavigationCompleted 呈现/清除（多标签串扰）
    private readonly Dictionary<string, string> _pendingDenyMessages = new();
    // CS-367（2026-10-01 审计）：KillSwitch 常驻横幅订阅句柄（OnClosed 解绑）
    private readonly Action _killSwitchEngagedHandler;
    // CS-393（2026-10-02 审计）：会话重建期抑制「集合清空即关窗」——
    // RestoreSavedSession 先关全部旧标签再重建，瞬时空集不得关窗
    private bool _restoringSession;

    private const string HomeUrl = Chrome.Ntp.NtpAssets.Url;

    // —— 集中管理的 UI 时序/阈值常量（审计修复：此前 150ms/30s/2.5s 等魔法数
    //    散落各处，调整需全文检索） ——
    private const int SleepCheckIntervalSec = 30;     // 后台标签睡眠巡检周期
    private const int FeedbackHideMs = 2500;          // 反馈条自动隐藏
    private const int SessionSaveDebounceMs = 2000;   // 会话落盘防抖（写放大治理）
    private const int BookmarkChipMaxChars = 14;      // 书签栏标题截断
    private const int BookmarkBarMaxChips = 20;       // CS-153：书签栏直显上限（其余收进溢出项）
    // CS-150：窗口状态恢复阈值（此前 400/300/1200/800 四个魔法数内联）
    private const double MinRestoredWidth = 400;
    private const double MinRestoredHeight = 300;
    // CS-333（2026-09-26 审计）：下载面板驻留上限——每个 DownloadItem 持有
    // 原生操作对象，集合只增不减时长会话无上限常驻；超限移除最早非进行中条目
    private const int MaxDownloadItems = 100;

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
        InitializeComponent();
        _runtimeCoordinator = new TabRuntimeCoordinator(_runtimes, WebViewHost);
        // 虚拟主机首帧重试耗尽：停止加载条并展示明确错误——瞬态抑制不应让
        // 加载条永久旋转，用户须能感知"虚拟主机资源无法加载"。
        _runtimeCoordinator.NtpNavigationFailed += OnNtpNavigationFailed;
        try { ApplyTheme(_settings.Theme); } catch (Exception ex) { Core.Security.SecurityLog.Write($"[theme] 应用主题失败（启动继续）: {ex.GetType().Name}: {ex.Message}"); }  // CS-234
        // CS-391：AccentBrush 缺省兜底（ApplyTheme 失败时 XAML DynamicResource
        // 仍有默认值可命中——与其它资源键同模式）
        if (!Resources.Contains("AccentBrush"))
            SetBrush("AccentBrush", "#FF0A84FF");
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
        // CS-367（2026-10-01 审计）：KillSwitch 触发后的常驻指示——此前紧急
        // 终止后主窗无任何提示（用户只见"导航没反应"无从知晓原因）。横幅
        // 一经显示不再隐藏（Engage 单向——重启恢复）
        _killSwitchEngagedHandler = () => Dispatcher.BeginInvoke(() =>
        {
            KillSwitchBanner.Visibility = Visibility.Visible;
        });
        _broker.KillSwitch.Engaged += _killSwitchEngagedHandler;
        if (_broker.KillSwitch.IsEngaged)
            KillSwitchBanner.Visibility = Visibility.Visible;
        ZoomStore.Load(_settings.ZoomByHost);
        // CS-261：BeginInvoke 非阻塞——ZoomStore.Changed 可能在非 UI 线程
        // 触发，Invoke 同步等待会造成跨线程阻塞面
        _zoomChangedHandler = () => Dispatcher.BeginInvoke(() => _settings.ZoomByHost = ZoomStore.Snapshot());
        ZoomStore.Changed += _zoomChangedHandler;
        // 设置单一事实源：统一持久化 + 刷新运行时 PrivacySettings
        _settingsService.Apply(_settings);
        _sessionSaver = new SessionSaveScheduler(
            new DispatcherDebounceTimer(),
            () => _sessionStore.Save(_tabs.Tabs, _tabs.CurrentTabId),
            TimeSpan.FromMilliseconds(SessionSaveDebounceMs));
        RestoreWindowState();
        StartSleepTimer();
    }

    /// <summary>截断标题而不劈开代理对（emoji 等——此前 b.Title[..14] 可把
    /// 双字符字形切成乱码）。CS-155：提 internal 直测。
    /// CS-395（2026-10-02 审计）：删除上叠挂的孤儿 summary（其描述的
    /// 「设置导航地址的统一容错入口」是 TabRuntime.Navigate 的契约，
    /// CS-038 时随代码迁移遗落在此）。</summary>
    internal static string TruncateTitle(string title, int maxChars)
    {
        if (title.Length <= maxChars)
            return title;
        var cut = maxChars;
        if (cut > 0 && char.IsHighSurrogate(title[cut - 1]))
            cut--;  // 高代理项必须与低代理项成对——退一位
        return title[..cut] + "…";
    }

    /// <summary>刷新书签栏（书签变更时重载）。</summary>
    // CS-278：书签 chip 样式实例字段缓存——资源键查询只做一次（此前每次
    // 全量重建书签栏都 FindResource）；主题由 DynamicResource 独立驱动不受影响
    private Style? _bookmarkChipStyle;

    public void RefreshBookmarkBar()
    {
        // 防御：样式资源缺失绝不能中断启动（history 回归 V3 教训——FindResource 抛
        // ResourceReferenceKeyNotFoundException，只要有书签就崩）。查不到时跳过样式。
        if (_bookmarkChipStyle is null)
        {
            try { _bookmarkChipStyle = (Style)FindResource("BookmarkBarButton"); }
            catch (Exception) { System.Diagnostics.Debug.WriteLine("BookmarkBarButton 资源缺失，使用默认按钮样式"); }
        }
        var chip = _bookmarkChipStyle;
        // CS-400（2026-10-02 审计）：书签全表查询（SQLite）移后台线程 + 回投——
        // 此前在 UI 线程同步 _bookmarks.All()（与 HistoryWindow CS-159 口径相悖，
        // 大书签库时开关管理器/编辑书签即冻结）；查询期间窗口关闭则丢弃结果
        Task.Run(() => _bookmarks.All())
            .ContinueWith(
                t => Dispatcher.BeginInvoke(
                    new Action(() =>
                    {
                        if (!IsLoaded)
                            return;  // 抓取期间窗口已关闭——不再触碰已卸载控件
                        RenderBookmarkBar(t.IsFaulted ? Array.Empty<Bookmark>() : t.Result, chip);
                    })));
    }

    /// <summary>CS-400：书签栏渲染（UI 线程——查询结果到 chip 的纯呈现段）。</summary>
    private void RenderBookmarkBar(IReadOnlyList<Bookmark> all, Style? chip)
    {
        BookmarkBarItems.Items.Clear();
        // CS-153：直显上限+溢出项——此前全部书签无上限重建（数百书签时
        // 栏内 chip 无限堆积挤压布局），超限部分收进「还有 N 条」溢出项
        foreach (var b in all.Take(BookmarkBarMaxChips))
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
                    TabRuntime.Navigate(rt, url);
            };
            BookmarkBarItems.Items.Add(btn);
        }
        var overflow = all.Count - BookmarkBarMaxChips;
        if (overflow > 0)
        {
            var more = new System.Windows.Controls.Button
            {
                Content = $"…还有 {overflow} 条",
                ToolTip = "在书签管理器中查看全部书签",
                Style = chip,
            };
            more.Click += (_, _) => BookmarkManager_Click(this, new RoutedEventArgs());
            BookmarkBarItems.Items.Add(more);
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
        // CS-391（2026-10-02 审计）：地址栏光标色资源键——此前 XAML 硬编码
        // #FFFFFFFF（浅色主题白底白光标不可见）；与 HistoryWindow/
        // BookmarkManagerWindow 的 AccentBrush 口径一致（深浅各自取值）
        SetBrush("AccentBrush", light ? "#FF0B57D0" : "#FF0A84FF");
        SetBrush("TextPrimaryBrush", light ? "#FF1A1A1A" : "#FFFFFFFF");
        SetBrush("TextSecondaryBrush", light ? "#FF5F6368" : "#B3FFFFFF");
        // 补齐子窗口依赖的画刷（默认深色值——各独立窗口资源键与主窗口统一）
        SetBrush("TextMutedBrush", light ? "#FF8A8A8E" : "#6CFFFFFF");
        SetBrush("SegmentedBrush", light ? "#14000000" : "#1FFFFFFF");
        // CS-318（2026-09-26 审计）：错误页/反馈条浅色值——此前硬编码深色，
        // 浅色主题下割裂（DynamicResource 运行时刷）
        SetBrush("ErrorPanelBackgroundBrush", light ? "#FFFDECEC" : "#FF2A1215");
        SetBrush("ErrorPanelTextBrush", light ? "#FFB3261E" : "#FFFCA5A5");
        SetBrush("FeedbackInfoBackgroundBrush", light ? "#FFE7F6EC" : "#FF0F2A1B");
        SetBrush("FeedbackWarningBackgroundBrush", light ? "#FFFDECEC" : "#FF2A1215");
        SetBrush("FeedbackTextBrush", light ? "#FF1B7F3B" : "#FF86EFAC");
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

    /// <summary>M1-T2：威胁黑名单启动快照 + 订阅源后台刷新（上帝对象拆分·第六批——
    /// 编排外移 ThreatFeedCoordinator，注入策略/缓存/源解析/日志）。订阅源经
    /// 设置界面（_settings.ThreatFeedUrl）优先、环境变量 AEGIS_THREAT_FEED_URL 后备。</summary>
    private void StartThreatFeedRefresh()
    {
        new Core.Security.ThreatFeedCoordinator(
            applyHosts: hosts => _broker.UpdateBlockedHosts(hosts),
            cachePath: AppPaths.ThreatFeedCachePath,
            resolveFeedUrl: () => string.IsNullOrWhiteSpace(_settings.ThreatFeedUrl)
                ? Environment.GetEnvironmentVariable("AEGIS_THREAT_FEED_URL")
                : _settings.ThreatFeedUrl,
            log: message => Core.Security.SecurityLog.Write(message)).Start();
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

    /// <summary>会话标脏（防抖 2s）：每次导航完成/开关标签只是重启计时——此前
    /// 每次导航完成同步写 SQLite（每页加载两写：历史一条 + 会话全量重写，长会话
    /// 写放大）。恢复抑制与到期落盘在 SessionSaveScheduler。</summary>
    private void SaveSession() => _sessionSaver.MarkDirty();

    /// <summary>立即落盘（窗口关闭/正常退出路径——防抖未到期的脏数据不丢）。</summary>
    private void FlushSession() => _sessionSaver.Flush();

    // ================= M3 会话恢复（新标签页手动入口） =================

    /// <summary>M3：手动恢复上次会话（NTP「恢复上次会话」按钮——重启后
    /// 重开上次页面集合；自动恢复仍由启动流程承担）。恢复期间抑制落盘
    /// （关闭现有标签会触发标脏，否则会覆盖即将恢复的快照）。</summary>
    private void RestoreSavedSession()
    {
        var saved = _sessionStore.Load(out var currentTabId);
        if (saved.Count == 0)
        {
            ShowFeedback("没有可恢复的已保存会话", isWarning: true);
            return;
        }
        using (_sessionSaver.BeginRestore())
        {
            // CS-393：重建期守卫——清空旧标签的瞬时空集不触发关窗
            _restoringSession = true;
            try
            {
                foreach (var tab in _tabs.Tabs.ToList())
                    _tabs.CloseTab(tab.TabId);
            }
            finally
            {
                _restoringSession = false;
            }
            RebuildTabsFromSnapshot(saved, currentTabId);
        }
        SaveSession();
        ShowFeedback($"已恢复上次会话（{saved.Count} 个标签）");
    }

    // CS-152：反馈条背景经主题资源键取用——ApplyTheme 已按主题写入
    // FeedbackInfo/WarningBackgroundBrush（CS-318 前为代码侧冻结刷，浅色主题
    // 下不随主题切换）；字典命中返回同一冻结实例，无每次调用分配
    /// <summary>反馈条显示（2.5s 自动隐藏——不静默原则的轻量实现）。</summary>
    private void ShowFeedback(string message, bool isWarning = false)
    {
        FeedbackText.Text = message;
        FeedbackBar.Background = (System.Windows.Media.Brush)Resources[
            isWarning ? "FeedbackWarningBackgroundBrush" : "FeedbackInfoBackgroundBrush"];
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

}

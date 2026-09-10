namespace Aegis.Windows.Chrome.Ntp;

using System;
using System.Collections.Generic;
using System.Linq;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Settings;
using Aegis.Windows.Core.Tabs;

/// <summary>NTP 宿主桥组装工厂（MainWindow 上帝对象拆分·第二批）：把 15 项
/// 服务委托的组装从主窗口外移。数据服务（书签/历史/设置/会话）由工厂统一
/// 持有；每标签差异（navigate/goBack/openGeo 作用于哪个 WebView）经
/// <see cref="Create"/> 注入。来源过滤为纯静态——可单测。</summary>
public sealed class NtpBridgeFactory
{
    private readonly AppSettings _settings;
    private readonly SettingsService _settingsService;
    private readonly BookmarkStore _bookmarks;
    private readonly HistoryStore _history;
    private readonly TabSessionStore _sessionStore;
    private readonly Action _restoreSession;
    private readonly Action<string> _syncEngineSelection;

    public NtpBridgeFactory(
        AppSettings settings,
        SettingsService settingsService,
        BookmarkStore bookmarks,
        HistoryStore history,
        TabSessionStore sessionStore,
        Action restoreSession,
        Action<string> syncEngineSelection)
    {
        _settings = settings ?? throw new ArgumentNullException(nameof(settings));
        _settingsService = settingsService ?? throw new ArgumentNullException(nameof(settingsService));
        _bookmarks = bookmarks ?? throw new ArgumentNullException(nameof(bookmarks));
        _history = history ?? throw new ArgumentNullException(nameof(history));
        _sessionStore = sessionStore ?? throw new ArgumentNullException(nameof(sessionStore));
        _restoreSession = restoreSession ?? throw new ArgumentNullException(nameof(restoreSession));
        _syncEngineSelection = syncEngineSelection ?? throw new ArgumentNullException(nameof(syncEngineSelection));
    }

    /// <summary>为指定标签组装宿主桥（每标签一份委托；数据服务共享单源）。</summary>
    public NtpBridge Create(TabRuntime runtime) => new(BuildServices(runtime));

    private NtpBridge.Services BuildServices(TabRuntime runtime) => new(
        SearchEngine: () => _settings.SearchEngine,
        SetSearchEngine: engine =>
        {
            _settings.SearchEngine = engine;
            _settingsService.Apply(_settings);
            _syncEngineSelection(engine);
        },
        Wallpaper: () => string.IsNullOrWhiteSpace(_settings.NtpWallpaper)
            ? NtpAssets.DefaultWallpaper
            : _settings.NtpWallpaper,
        SetWallpaper: name =>
        {
            _settings.NtpWallpaper = name;
            _settingsService.Apply(_settings);
        },
        Bookmarks: () => _bookmarks.All(),
        SavedSessionCount: () => _sessionStore.Load().Count,
        RestoreSession: _restoreSession,
        Navigate: target =>
        {
            // 桥已归一（非导航协议 fail-closed）——此处直接进入
            // NavigationStarting→broker 唯一授权路径
            SafeNavigate(runtime, target);
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
            if (NtpAssets.ResolveGeoRoot() is null)
                return false;  // 资源未随包——fail-closed 降级（按钮置灰）
            return SafeNavigate(runtime,
                $"https://{NtpAssets.GeoHostName}/{NtpAssets.GeoEntryPath}");
        },
        ImportSources: () =>
        {
            // 探测 = 仅文件存在性检查（不读取内容）；书签/历史能力按来源汇总
            var byBrowser = new Dictionary<string, (bool Bookmarks, bool History)>();
            foreach (var source in BookmarkImporter.DetectSources())
                byBrowser[source.Browser] = (true, false);
            foreach (var source in HistoryImporter.DetectSources())
                byBrowser[source.Browser] = byBrowser.TryGetValue(source.Browser, out var known)
                    ? (known.Bookmarks, true)
                    : (false, true);
            var sources = new List<NtpBridge.ImportSourceSnapshot>();
            foreach (var pair in byBrowser)
                sources.Add(new(pair.Key, pair.Value.Bookmarks, pair.Value.History));
            return sources;
        },
        ImportBookmarks: sourceFilter =>
        {
            var imported = 0;
            var total = 0;
            var results = new List<NtpBridge.ImportResult>();
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
                catch (Exception ex)
                {
                    // 单来源失败不阻断其余来源（可选功能——对齐 Python 口径）
                    Core.Security.SecurityLog.Write(
                        $"[import] 书签来源 {source.Browser} 导入失败: {ex.GetType().Name}: {ex.Message}");
                }
            }
            return (imported, total, results);
        },
        ImportHistory: (limit, sourceFilter) =>
        {
            var imported = 0;
            var total = 0;
            var results = new List<NtpBridge.ImportResult>();
            foreach (var source in FilterSources(HistoryImporter.DetectSources(), sourceFilter, s => s.Browser))
            {
                try
                {
                    var candidates = HistoryImporter.Parse(source.Path, limit);
                    var (one, all) = HistoryImporter.ImportTo(_history, candidates);
                    results.Add(new(source.Browser, one, all));
                    imported += one;
                    total += all;
                }
                catch (Exception ex)
                {
                    // 单来源失败不阻断其余来源（可选功能——对齐 Python 口径）
                    Core.Security.SecurityLog.Write(
                        $"[import] 历史来源 {source.Browser} 导入失败: {ex.GetType().Name}: {ex.Message}");
                }
            }
            return (imported, total, results);
        });

    /// <summary>导航的统一容错入口（地址非法/控件已释放时拒绝而不是抛异常）。</summary>
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

    /// <summary>导入来源过滤（纯函数——空/all = 全部来源；否则仅指定浏览器）。</summary>
    public static IEnumerable<T> FilterSources<T>(
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
}

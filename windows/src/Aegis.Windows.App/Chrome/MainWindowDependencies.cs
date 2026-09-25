namespace Aegis.Windows.Chrome;

using Aegis.Windows.Broker;
using Aegis.Windows.Core;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.Downloads;
using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Settings;
using Aegis.Windows.Core.Tabs;

/// <summary>主窗口构造依赖（组合根在 App.xaml.cs 装配——MainWindow 不再自建
/// 存储/策略/broker，可注入可测，存储可换内存实现）。字段为 .NET 10 primary
/// record 构造参数。</summary>
public sealed record MainWindowDependencies(
    TabManager Tabs,
    BrowserPolicyBroker Broker,
    AppSettings Settings,
    SettingsService SettingsService,
    BookmarkStore Bookmarks,
    HistoryStore History,
    TabSessionStore SessionStore,
    DownloadRecordStore DownloadRecords)
{
    /// <summary>对齐旧行为的分发（SessionDbPath 等 AppPaths 默认路径）。
    /// CS-127：settings.json 单读双用——AppSettings.Load 读到的模型经
    /// SettingsService.FromPreloaded 复用，不再由服务构造器二次读盘。</summary>
    public static MainWindowDependencies Defaults()
    {
        var settings = AppSettings.Load(AppSettings.DefaultPath);
        return new MainWindowDependencies(
            Tabs: new TabManager(),
            Broker: new BrowserPolicyBroker(),
            Settings: settings,
            SettingsService: SettingsService.FromPreloaded(settings),
            Bookmarks: new BookmarkStore(AppPaths.BookmarksDbPath),
            History: new HistoryStore(AppPaths.HistoryDbPath),
            SessionStore: new TabSessionStore(AppPaths.SessionDbPath),
            DownloadRecords: new DownloadRecordStore(AppPaths.DownloadsDbPath));
    }
}
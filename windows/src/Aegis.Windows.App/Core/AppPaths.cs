namespace Aegis.Windows.Core;

using System;
using System.IO;

/// <summary>C# 栈数据目录解析（ADR-009：与 Python stable 渠道的数据目录
/// 隔离——beta 渠道独立存储，避免跨渠道读写干扰）。
/// 存储布局单源：全部数据文件路径在此定义（此前 bookmarks/history/downloads
/// /favicons 路径散落在 MainWindow/FaviconService 各自 Path.Combine）。
/// 环境变量 AEGIS_DATA_DIR 可覆盖（便携模式/测试隔离）；系统目录不可用时
/// 回退当前目录（漫游/容器环境 GetFolderPath 可返回空串——此前退化为
/// 挂在当前盘根的 \Aegis\AegisCSharp）。</summary>
public static class AppPaths
{
    private static readonly string DataDirValue = ResolveDataDir();

    private static string ResolveDataDir()
    {
        var overrideDir = Environment.GetEnvironmentVariable("AEGIS_DATA_DIR");
        if (!string.IsNullOrWhiteSpace(overrideDir))
            return overrideDir;
        var baseDir = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrWhiteSpace(baseDir))
            baseDir = AppContext.BaseDirectory;  // 容器/服务环境——退到应用目录
        return Path.Combine(baseDir, "Aegis", "AegisCSharp");
    }

    public static string DataDir => DataDirValue;

    public static string SessionDbPath => Path.Combine(DataDir, "tabs.db");
    public static string BookmarksDbPath => Path.Combine(DataDir, "bookmarks.db");
    public static string HistoryDbPath => Path.Combine(DataDir, "history.db");
    public static string DownloadsDbPath => Path.Combine(DataDir, "downloads.db");
    public static string FaviconsDir => Path.Combine(DataDir, "favicons");
    public static string ThreatFeedCachePath => Path.Combine(DataDir, "threat_feed.txt");
    public static string SecurityLogPath => Path.Combine(DataDir, "security.log");
}

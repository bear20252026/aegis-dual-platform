namespace Aegis.Windows.Core.Settings;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Aegis.Windows.Core.Privacy;

/// <summary>不可变的浏览器设置快照。快照是设置持久层与运行期策略的唯一事实源。</summary>
public sealed record BrowserSettingsSnapshot
{
    // CS-123：窗口宽高默认/边界单源——此前快照默认值与归一化回退值两套并存
    //（一处改动漏一处即宽高归一口径漂移），归一化与快照初始值都引用这里。
    public const double DefaultWindowWidth = 1200;
    public const double DefaultWindowHeight = 800;
    public const double MinWindowWidth = 320;
    public const double MinWindowHeight = 240;
    public const double MaxWindowDimension = 10000;

    public string SearchEngine { get; init; } = Chrome.UrlNormalizer.DefaultEngine;
    public bool HistoryEnabled { get; init; } = true;
    public string ThreatFeedUrl { get; init; } = "";
    public string NtpWallpaper { get; init; } = "";
    public string Theme { get; init; } = "dark";
    public double WindowLeft { get; init; } = double.NaN;
    public double WindowTop { get; init; } = double.NaN;
    public double WindowWidth { get; init; } = DefaultWindowWidth;
    public double WindowHeight { get; init; } = DefaultWindowHeight;
    public bool WindowMaximized { get; init; }
    public int SleepMinutes { get; init; } = 30;
    public int ProtectionLevel { get; init; } = 1;
    public bool HttpsOnly { get; init; } = true;
    public bool SecureDns { get; init; } = true;
    public IReadOnlyDictionary<string, double> ZoomByHost { get; init; } =
        new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
}

/// <summary>统一 AppSettings 与 PrivacySettings 的设置服务。</summary>
public sealed class SettingsService
{
    /// <summary>CS-122：睡眠阈值白名单（设置下拉可选项集——此前内联字面量
    /// 散在归一化表达式里，下拉项与归一口径无单一事实源）。</summary>
    private static readonly int[] AllowedSleepMinutes = [0, 15, 30, 60];

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals,
    };
    private readonly string _path;
    private BrowserSettingsSnapshot _snapshot;

    public SettingsService(string? path = null)
    {
        _path = path ?? AppSettings.DefaultPath;
        _snapshot = Normalize(ReadSnapshot(_path));
        ApplyRuntimeSnapshot(_snapshot, raiseChanged: false);
    }

    private SettingsService(string? path, AppSettings preloaded)
    {
        _path = path ?? AppSettings.DefaultPath;
        _snapshot = Normalize(ToSnapshot(preloaded));
        ApplyRuntimeSnapshot(_snapshot, raiseChanged: false);
    }

    /// <summary>CS-127：从已加载模型构造——组合根（AppSettings.Load）与本服务
    /// 此前各读一次同一 settings.json（启动链双读）；现在单读双用。</summary>
    public static SettingsService FromPreloaded(AppSettings preloaded, string? path = null) =>
        new(path, preloaded);

    public BrowserSettingsSnapshot Snapshot => _snapshot;
    public event EventHandler? Changed;

    /// <summary>从 AppSettings 模型应用并持久化——设置变更的唯一写入口：
    /// 归一化 → 原子写盘（失败不阻断、不改动运行时——内存/磁盘不分叉）→
    /// 刷新运行时 PrivacySettings → 通知。</summary>
    public void Apply(AppSettings model)
    {
        var snapshot = Normalize(ToSnapshot(model));
        SaveCore(snapshot);
        _snapshot = snapshot;
        PrivacySettings.ProtectionLevel = snapshot.ProtectionLevel;
        PrivacySettings.HttpsOnly = snapshot.HttpsOnly;
        PrivacySettings.SecureDns = snapshot.SecureDns;
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private void SaveCore(BrowserSettingsSnapshot normalized)
    {
        try
        {
            var dir = Path.GetDirectoryName(_path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            var temp = _path + ".tmp." + Guid.NewGuid().ToString("N");
            try
            {
                File.WriteAllText(temp, JsonSerializer.Serialize(ToAppSettings(normalized), JsonOptions));
                if (File.Exists(_path)) File.Replace(temp, _path, null);
                else File.Move(temp, _path);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        catch (Exception ex)
        {
            // 写盘失败（磁盘满/被备份软件锁定）不再向 UI 事件上抛——每次导航/
            // 缩放都会触发保存，上抛即重复全局异常弹窗
            Security.SecurityLog.Write(
                $"[settings] 保存失败（内存态保持，下次保存重试）: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private void ApplyRuntimeSnapshot(BrowserSettingsSnapshot snapshot, bool raiseChanged)
    {
        var previous = _snapshot;
        _snapshot = snapshot;
        PrivacySettings.ProtectionLevel = snapshot.ProtectionLevel;
        PrivacySettings.HttpsOnly = snapshot.HttpsOnly;
        PrivacySettings.SecureDns = snapshot.SecureDns;
        if (raiseChanged && !ReferenceEquals(previous, snapshot)) Changed?.Invoke(this, EventArgs.Empty);
    }

    private static BrowserSettingsSnapshot ReadSnapshot(string path)
    {
        try
        {
            if (!File.Exists(path)) return new BrowserSettingsSnapshot();
            var model = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(path), JsonOptions);
            return ToSnapshot(model ?? new AppSettings());
        }
        catch (Exception ex)
        {
            Security.SecurityLog.Write(
                $"[settings] 快照读取失败（回退默认）: {ex.GetType().Name}: {ex.Message}");
            return new BrowserSettingsSnapshot();
        }
    }

    private static AppSettings ToAppSettings(BrowserSettingsSnapshot s)
    {
        var model = new AppSettings
        {
            SearchEngine = s.SearchEngine,
            HistoryEnabled = s.HistoryEnabled,
            ThreatFeedUrl = s.ThreatFeedUrl,
            NtpWallpaper = s.NtpWallpaper,
            Theme = s.Theme,
            WindowLeft = s.WindowLeft,
            WindowTop = s.WindowTop,
            WindowWidth = s.WindowWidth,
            WindowHeight = s.WindowHeight,
            WindowMaximized = s.WindowMaximized,
            SleepMinutes = s.SleepMinutes,
            ProtectionLevel = s.ProtectionLevel,
            HttpsOnly = s.HttpsOnly,
            SecureDns = s.SecureDns,
        };
        foreach (var p in s.ZoomByHost)
            model.ZoomByHost[p.Key] = p.Value;
        return model;
    }

    private static BrowserSettingsSnapshot ToSnapshot(AppSettings m) => new()
    {
        SearchEngine = m.SearchEngine,
        HistoryEnabled = m.HistoryEnabled,
        ThreatFeedUrl = m.ThreatFeedUrl,
        NtpWallpaper = m.NtpWallpaper,
        Theme = m.Theme,
        WindowLeft = m.WindowLeft,
        WindowTop = m.WindowTop,
        WindowWidth = m.WindowWidth,
        WindowHeight = m.WindowHeight,
        WindowMaximized = m.WindowMaximized,
        SleepMinutes = m.SleepMinutes,
        ProtectionLevel = m.ProtectionLevel,
        HttpsOnly = m.HttpsOnly,
        SecureDns = m.SecureDns,
        // null 防护：settings.json 手编为 "ZoomByHost": null 时此前抛
        // ArgumentNullException 且发生在启动链上（应用无法启动）
        ZoomByHost = new Dictionary<string, double>(
            m.ZoomByHost ?? new Dictionary<string, double>(), StringComparer.OrdinalIgnoreCase),
    };

    private static BrowserSettingsSnapshot Normalize(BrowserSettingsSnapshot s)
    {
        var engine = Chrome.UrlNormalizer.EngineOrder.Contains(s.SearchEngine, StringComparer.OrdinalIgnoreCase)
            ? s.SearchEngine.ToLowerInvariant() : Chrome.UrlNormalizer.DefaultEngine;
        var theme = string.Equals(s.Theme, "light", StringComparison.OrdinalIgnoreCase) ? "light" : "dark";
        var sleep = Array.IndexOf(AllowedSleepMinutes, s.SleepMinutes) >= 0 ? s.SleepMinutes : 30;
        var protection = Math.Clamp(s.ProtectionLevel, 0, 2);
        var left = NormalizeWindow(s.WindowLeft, double.NaN, -100000, 100000);
        var top = NormalizeWindow(s.WindowTop, double.NaN, -100000, 100000);
        var width = NormalizeWindow(s.WindowWidth, BrowserSettingsSnapshot.DefaultWindowWidth,
            BrowserSettingsSnapshot.MinWindowWidth, BrowserSettingsSnapshot.MaxWindowDimension);
        var height = NormalizeWindow(s.WindowHeight, BrowserSettingsSnapshot.DefaultWindowHeight,
            BrowserSettingsSnapshot.MinWindowHeight, BrowserSettingsSnapshot.MaxWindowDimension);
        var feed = Security.ThreatFeedUpdater.ValidateFeedUrl(s.ThreatFeedUrl ?? "") is null
            ? "" : (s.ThreatFeedUrl ?? "");
        var zoom = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in s.ZoomByHost ?? new Dictionary<string, double>())
            if (!string.IsNullOrWhiteSpace(p.Key) && double.IsFinite(p.Value))
                // 与会话内缩放同口径 0.25–3.0（此前钳 1.0–3.0：用户缩到 75%
                // 后任意设置变更即被静默重置为 100%）
                zoom[p.Key] = Math.Clamp(p.Value, Chrome.TabRuntime.MinZoom, Chrome.TabRuntime.MaxZoom);
        return s with { SearchEngine = engine, Theme = theme, SleepMinutes = sleep,
            ProtectionLevel = protection, WindowLeft = left, WindowTop = top,
            WindowWidth = width, WindowHeight = height, ThreatFeedUrl = feed, ZoomByHost = zoom };
    }

    private static double NormalizeWindow(double value, double fallback, double min = 0, double max = 100000)
        => double.IsNaN(value) ? fallback : (double.IsFinite(value) ? Math.Clamp(value, min, max) : fallback);
}

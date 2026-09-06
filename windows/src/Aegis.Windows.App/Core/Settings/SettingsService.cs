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
    public string SearchEngine { get; init; } = Chrome.UrlNormalizer.DefaultEngine;
    public bool HistoryEnabled { get; init; } = true;
    public string ThreatFeedUrl { get; init; } = "";
    public string NtpWallpaper { get; init; } = "";
    public string Theme { get; init; } = "dark";
    public double WindowLeft { get; init; } = double.NaN;
    public double WindowTop { get; init; } = double.NaN;
    public double WindowWidth { get; init; } = 1200;
    public double WindowHeight { get; init; } = 800;
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

    public BrowserSettingsSnapshot Snapshot => _snapshot;
    public event EventHandler? Changed;

    public static SettingsService Load(string? path = null) => new(path);

    public void Save() => Save(_snapshot);

    /// <summary>从 AppSettings 模型应用并持久化——设置变更的唯一写入口：
    /// 归一化 → 刷新运行时 PrivacySettings → 原子写盘 → 通知。</summary>
    public void Apply(AppSettings model)
    {
        var snapshot = Normalize(ToSnapshot(model));
        _snapshot = snapshot;
        PrivacySettings.ProtectionLevel = snapshot.ProtectionLevel;
        PrivacySettings.HttpsOnly = snapshot.HttpsOnly;
        PrivacySettings.SecureDns = snapshot.SecureDns;
        SaveCore(snapshot);
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public void Save(BrowserSettingsSnapshot snapshot)
    {
        var normalized = Normalize(snapshot);
        SaveCore(normalized);
        ApplyRuntimeSnapshot(normalized);
    }

    private void SaveCore(BrowserSettingsSnapshot normalized)
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

    public void ApplyRuntimeSnapshot(BrowserSettingsSnapshot snapshot) =>
        ApplyRuntimeSnapshot(Normalize(snapshot), raiseChanged: true);

    private void ApplyRuntimeSnapshot(BrowserSettingsSnapshot snapshot, bool raiseChanged)
    {
        var previous = _snapshot;
        _snapshot = snapshot;
        PrivacySettings.ProtectionLevel = snapshot.ProtectionLevel;
        PrivacySettings.HttpsOnly = snapshot.HttpsOnly;
        PrivacySettings.SecureDns = snapshot.SecureDns;
        if (raiseChanged && !Equals(previous, snapshot)) Changed?.Invoke(this, EventArgs.Empty);
    }

    private static BrowserSettingsSnapshot ReadSnapshot(string path)
    {
        try
        {
            if (!File.Exists(path)) return new BrowserSettingsSnapshot();
            var model = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(path), JsonOptions);
            return ToSnapshot(model ?? new AppSettings());
        }
        catch (IOException) { return new BrowserSettingsSnapshot(); }
        catch (JsonException) { return new BrowserSettingsSnapshot(); }
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
        ZoomByHost = new Dictionary<string, double>(m.ZoomByHost, StringComparer.OrdinalIgnoreCase),
    };

    private static BrowserSettingsSnapshot Normalize(BrowserSettingsSnapshot s)
    {
        var engine = Chrome.UrlNormalizer.EngineOrder.Contains(s.SearchEngine, StringComparer.OrdinalIgnoreCase)
            ? s.SearchEngine.ToLowerInvariant() : Chrome.UrlNormalizer.DefaultEngine;
        var theme = string.Equals(s.Theme, "light", StringComparison.OrdinalIgnoreCase) ? "light" : "dark";
        var sleep = s.SleepMinutes is 0 or 15 or 30 or 60 ? s.SleepMinutes : 30;
        var protection = Math.Clamp(s.ProtectionLevel, 0, 2);
        var left = NormalizeWindow(s.WindowLeft, double.NaN);
        var top = NormalizeWindow(s.WindowTop, double.NaN);
        var width = NormalizeWindow(s.WindowWidth, 1200, 320, 10000);
        var height = NormalizeWindow(s.WindowHeight, 800, 240, 10000);
        var zoom = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in s.ZoomByHost ?? new Dictionary<string, double>())
            if (!string.IsNullOrWhiteSpace(p.Key) && double.IsFinite(p.Value))
                zoom[p.Key] = Math.Clamp(p.Value, 1.0, 3.0);
        return s with { SearchEngine = engine, Theme = theme, SleepMinutes = sleep,
            ProtectionLevel = protection, WindowLeft = left, WindowTop = top,
            WindowWidth = width, WindowHeight = height, ZoomByHost = zoom };
    }

    private static double NormalizeWindow(double value, double fallback, double min = 0, double max = 100000)
        => double.IsNaN(value) ? fallback : (double.IsFinite(value) ? Math.Clamp(value, min, max) : fallback);
}

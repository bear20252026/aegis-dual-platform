namespace Aegis.Windows.Core.Tests;

using System.IO;
using Aegis.Windows.Core.Privacy;
using Aegis.Windows.Core.Settings;
using Xunit;

/// <summary>SettingsService 单一事实源回归：往返、归一化边界、原子保存、
/// PrivacySettings 同步。修复「AppSettings 与 PrivacySettings 双事实源」。</summary>
public sealed class SettingsServiceTests : IDisposable
{
    private readonly string _path = Path.Combine(Path.GetTempPath(), $"settings_{Guid.NewGuid():N}.json");

    [Fact]
    public void ApplyPersistsAndRoundTrips()
    {
        var svc = new SettingsService(_path);
        svc.Apply(new AppSettings { SearchEngine = "bing", Theme = "light", HttpsOnly = false });

        var reloaded = new SettingsService(_path);
        Assert.Equal("bing", reloaded.Snapshot.SearchEngine);
        Assert.Equal("light", reloaded.Snapshot.Theme);
        Assert.False(reloaded.Snapshot.HttpsOnly);
    }

    [Fact]
    public void NormalizeCorrectsInvalidValues()
    {
        var svc = new SettingsService(_path);
        svc.Apply(new AppSettings
        {
            SearchEngine = "not-a-real-engine",
            Theme = "neon",
            SleepMinutes = 99,
            ProtectionLevel = 9,
        });

        Assert.Equal(Chrome.UrlNormalizer.DefaultEngine, svc.Snapshot.SearchEngine);
        Assert.Equal("dark", svc.Snapshot.Theme);
        Assert.Equal(30, svc.Snapshot.SleepMinutes);
        Assert.Equal(2, svc.Snapshot.ProtectionLevel);
    }

    [Fact]
    public void ApplyUpdatesRuntimePrivacySnapshot()
    {
        var svc = new SettingsService(_path);
        svc.Apply(new AppSettings { ProtectionLevel = 2, HttpsOnly = false, SecureDns = false });

        Assert.Equal(2, PrivacySettings.ProtectionLevel);
        Assert.False(PrivacySettings.HttpsOnly);
    }

    [Fact]
    public void AtomicSaveLeavesValidJson()
    {
        var svc = new SettingsService(_path);
        svc.Apply(new AppSettings { SearchEngine = "google" });

        var text = File.ReadAllText(_path);
        Assert.Contains("\"SearchEngine\"", text);
        Assert.Contains("google", text);
    }

    [Fact]
    public void MissingFileDefaultsAndNaNCompatible()
    {
        var svc = new SettingsService(_path);
        var s = svc.Snapshot;
        Assert.Equal("baidu", s.SearchEngine);
        Assert.True(double.IsNaN(s.WindowLeft));
        Assert.True(double.IsNaN(s.WindowTop));
    }

    // ===== CS-075（审计 2026-09-25）：写盘失败不抛且内存快照已更新 =====

    [Fact]
    public void ApplyWithUnwritablePathDoesNotThrowAndUpdatesSnapshot()
    {
        // _path 指向一个已存在的目录——File.Move 必然失败（磁盘满/文件被锁的
        // 等价模拟）。契约：异常被吞（每次导航/缩放都触发保存，上抛即重复弹窗）、
        // 内存快照仍然更新（内存/磁盘不分叉——下次保存重试）、Changed 仍通知。
        var dirPath = Path.Combine(Path.GetTempPath(), $"settings_dir_{Guid.NewGuid():N}");
        Directory.CreateDirectory(dirPath);
        try
        {
            var svc = new SettingsService(dirPath);
            var changed = 0;
            svc.Changed += (_, _) => changed++;

            var ex = Record.Exception(() => svc.Apply(new AppSettings { SearchEngine = "bing" }));

            Assert.Null(ex);
            Assert.Equal("bing", svc.Snapshot.SearchEngine);
            Assert.Equal(1, changed);
        }
        finally
        {
            try { Directory.Delete(dirPath); } catch (IOException) { }
        }
    }

    public void Dispose()
    {
        try { File.Delete(_path); } catch (IOException) { }
    }
}
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

    public void Dispose()
    {
        try { File.Delete(_path); } catch (IOException) { }
    }
}
namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Settings;
using Xunit;

/// <summary>M2（ADR-009）：历史存储（FTS5/清除）与设置持久化单测。</summary>
public sealed class HistoryStoreTests : IDisposable
{
    private readonly string _dbPath =
        Path.Combine(Path.GetTempPath(), $"aegis_hist_{Guid.NewGuid():N}.db");
    private readonly HistoryStore _store;

    public HistoryStoreTests() => _store = new HistoryStore(_dbPath);

    [Fact]
    public void AddThenRecentReturnsEntriesNewestFirst()
    {
        _store.Add("https://first.example", "第一页");
        _store.Add("https://second.example", "第二页");

        var recent = _store.Recent(10);

        Assert.Equal(2, recent.Count);
        Assert.Equal("https://second.example", recent[0].Url);
    }

    [Fact]
    public void FullTextSearchMatchesTitleAndUrl()
    {
        _store.Add("https://animals.example/zoo", "国家动物博物馆");
        _store.Add("https://plants.example", "植物园");

        var hits = _store.Search("动物");
        Assert.Single(hits);
        Assert.Equal("https://animals.example/zoo", hits[0].Url);

        var urlHits = _store.Search("plants");
        Assert.Single(urlHits);
    }

    [Fact]
    public void SearchMalformedQueryFallsBackToLike()
    {
        // FTS5 MATCH 语法错误（裸引号等）→ LIKE 回退，不抛异常（fail-safe）
        _store.Add("https://weird.example", "带\"引号\"的页");
        var hits = _store.Search("\"引号");
        Assert.NotEmpty(hits);
    }

    [Fact]
    public void ClearRemovesEverything()
    {
        _store.Add("https://a.example", "A");
        _store.Add("https://b.example", "B");
        _store.Clear();
        Assert.Empty(_store.Recent(100));
    }

    [Fact]
    public void BlankUrlIgnored()
    {
        _store.Add("", "空");
        Assert.Empty(_store.Recent(10));
    }

    public void Dispose()
    {
        if (File.Exists(_dbPath))
            File.Delete(_dbPath);
    }
}

/// <summary>AppSettings 持久化 round-trip + 非法值回退。</summary>
public sealed class AppSettingsTests : IDisposable
{
    private readonly string _path =
        Path.Combine(Path.GetTempPath(), $"aegis_settings_{Guid.NewGuid():N}.json");

    [Fact]
    public void SaveLoadRoundTrip()
    {
        new AppSettings { SearchEngine = "google", HistoryEnabled = false }.Save(_path);
        var loaded = AppSettings.Load(_path);
        Assert.Equal("google", loaded.SearchEngine);
        Assert.False(loaded.HistoryEnabled);
    }

    [Fact]
    public void MissingFileReturnsDefaults()
    {
        var loaded = AppSettings.Load(Path.Combine(Path.GetTempPath(), $"no_such_{Guid.NewGuid():N}.json"));
        Assert.Equal("baidu", loaded.SearchEngine);
        Assert.True(loaded.HistoryEnabled);
    }

    [Fact]
    public void CorruptedFileReturnsDefaultsFailSafe()
    {
        File.WriteAllText(_path, "{ not valid json");
        var loaded = AppSettings.Load(_path);
        Assert.Equal("baidu", loaded.SearchEngine);
    }

    public void Dispose()
    {
        if (File.Exists(_path))
            File.Delete(_path);
    }
}

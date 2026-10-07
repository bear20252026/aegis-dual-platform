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

    [Fact]
    public void SearchMultiWordQueryTreatedAsLiteralSubstring()
    {
        // CS-019：多词查询按整串子串语义（空格不切词）——锁定 LIKE 回退路径的口径
        _store.Add("https://zoo.example/国家动物博物馆", "标题");

        Assert.Single(_store.SearchByUrl("国家动物"));
        Assert.Empty(_store.SearchByUrl("国家 动物"));  // 带空格整串不命中
    }

    [Fact]
    public void SearchCaseInsensitiveForAscii()
    {
        // CS-020：ASCII 大小写不敏感（SQLite LIKE 默认语义锁定）。
        // 观测口径走生产在用的 SearchByUrl——原 Search 的标题列匹配随死面一并移除。
        _store.Add("https://GitHub.Example/Repo", "MyPage");
        Assert.Single(_store.SearchByUrl("github"));
        Assert.Single(_store.SearchByUrl("GITHUB.Example"));
    }

    [Fact]
    public void ClearResetsCountToZero()
    {
        // CS-024：Clear 后 Count 必须归零（组合断言——分页条总页数不残留）
        _store.Add("https://a.example", "A");
        _store.Add("https://b.example", "B");
        Assert.Equal(2, _store.Count(null, null, null));

        _store.Clear();
        Assert.Equal(0, _store.Count(null, null, null));
        Assert.Empty(_store.Recent(100));
    }

    [Fact]
    public void AddReturnsFalseWithoutThrowWhenDiskFails()
    {
        // CS-025：dbPath 指向目录（SQLite 无法建库）——Add 返回 false 不抛
        var store = new HistoryStore(Path.GetTempPath());
        Assert.False(store.Add("https://x.example", "x"));
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

namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>M1-T1（ADR-009）：TabSessionStore 持久化 round-trip 单测
/// （SQLite——ADR-009 D2 数据层统一决策）。</summary>
public sealed class TabSessionStoreTests : IDisposable
{
    private readonly string _dbPath =
        Path.Combine(Path.GetTempPath(), $"aegis_tabs_{Guid.NewGuid():N}.db");

    [Fact]
    public void SaveThenLoadRoundTripsTabsAndCurrent()
    {
        var store = new TabSessionStore(_dbPath);
        var tabs = new List<Tab>
        {
            new("tab-a", "https://a.example", "A"),
            new("tab-b", "https://b.example/page?x=1", "B"),
        };

        store.Save(tabs, "tab-b");
        var loaded = store.Load(out var currentTabId);

        Assert.Equal(2, loaded.Count);
        Assert.Equal("tab-a", loaded[0].TabId);
        Assert.Equal("https://a.example", loaded[0].Url);
        Assert.Equal("B", loaded[1].Title);
        Assert.Equal("https://b.example/page?x=1", loaded[1].Url);
        Assert.Equal("tab-b", currentTabId);
    }

    [Fact]
    public void MissingCurrentMarkerFallsBackToLastTab()
    {
        var store = new TabSessionStore(_dbPath);
        store.Save([new("tab-a", "https://a.example", "A")], null);

        store.Load(out var currentTabId);

        Assert.Equal("tab-a", currentTabId);
    }

    [Fact]
    public void OverwriteReplacesPreviousSession()
    {
        var store = new TabSessionStore(_dbPath);
        store.Save([new("tab-old", "https://old.example", "old")], "tab-old");
        store.Save([new("tab-new", "https://new.example", "new")], "tab-new");

        var loaded = store.Load();

        Assert.Single(loaded);
        Assert.Equal("tab-new", loaded[0].TabId);
    }

    [Fact]
    public void MissingDatabaseLoadsEmpty()
    {
        var store = new TabSessionStore(_dbPath);

        var loaded = store.Load(out var currentTabId);

        Assert.Empty(loaded);
        Assert.Null(currentTabId);
    }

    [Fact]
    public void SaveEmptyListClearsPreviousSession()
    {
        // CS-187：空列表保存=清空会话（重启后不复活已关闭的旧标签）
        var store = new TabSessionStore(_dbPath);
        store.Save(
        [
            new("tab-a", "https://a.example", "A"),
            new("tab-b", "https://b.example", "B"),
        ], "tab-a");

        store.Save([], null);
        var loaded = store.Load(out var currentTabId);

        Assert.Empty(loaded);
        Assert.Null(currentTabId);
    }

    [Fact]
    public void CorruptedCurrentMarkerFallsBackToLastRow()
    {
        // CS-188：is_current 标记被损坏清零（部分写/外部篡改）→ 末位标签生效，
        // 不抛异常也不产生 null current
        var store = new TabSessionStore(_dbPath);
        store.Save(
        [
            new("tab-a", "https://a.example", "A"),
            new("tab-b", "https://b.example", "B"),
            new("tab-c", "https://c.example", "C"),
        ], "tab-a");

        using (var connection = new Microsoft.Data.Sqlite.SqliteConnection(
            new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
            {
                DataSource = _dbPath,
                Pooling = false,  // 不入池——否则连接句柄长持文件，Dispose 删库失败
            }.ToString()))
        {
            connection.Open();
            using var cmd = connection.CreateCommand();
            cmd.CommandText = "UPDATE tabs SET is_current = 0";
            cmd.ExecuteNonQuery();
        }

        var loaded = store.Load(out var currentTabId);
        Assert.Equal(3, loaded.Count);
        Assert.Equal("tab-c", currentTabId);  // 末行兜底
    }

    [Fact]
    public void CorruptedDatabaseLoadsEmptyFailSafe()
    {
        // fail-safe 契约：库损坏 → 空会话（不阻断启动——绝不因恢复失败崩浏览器）
        Directory.CreateDirectory(Path.GetDirectoryName(_dbPath)!);
        File.WriteAllBytes(_dbPath, [0x00, 0x01, 0x02, 0x03]);
        var store = new TabSessionStore(_dbPath);

        var loaded = store.Load();

        Assert.Empty(loaded);
    }

    public void Dispose()
    {
        if (File.Exists(_dbPath))
            File.Delete(_dbPath);
    }
}

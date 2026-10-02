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
    public void IsPinnedRoundTrips()
    {
        // CS-250：固定态跨会话往返
        var store = new TabSessionStore(_dbPath);
        store.Save(
        [
            new("tab-a", "https://a.example", "A") { IsPinned = true },
            new("tab-b", "https://b.example", "B"),
        ], "tab-b");

        var loaded = store.Load(out _);

        Assert.True(loaded[0].IsPinned);
        Assert.False(loaded[1].IsPinned);
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

    // ===== CS-341/353（2026-10-01 审计）：会话保存钳制 + BLOB 行 fail-safe =====

    [Fact]
    public void Save_ClampsOverlongUrlAndTitle()
    {
        // CS-341：页面可控任意长 url/title 此前原样落 tabs.db（单页即可撑大
        // 库文件）；INSERT 前 2048/256 钳制（与书签/历史库同源口径）
        var store = new TabSessionStore(_dbPath);
        var longUrl = "https://example.com/" + new string('u', 3000);
        var longTitle = new string('题', 300);

        store.Save([new("tab-a", longUrl, longTitle)], "tab-a");
        var loaded = store.Load();

        var tab = Assert.Single(loaded);
        Assert.Equal(2048, tab.Url.Length);
        Assert.Equal(256, tab.Title.Length);
    }

    [Fact]
    public void CorruptedBlobRow_DoesNotThrowIntoStartup()
    {
        // CS-353（2026-10-01 核验）：Microsoft.Data.Sqlite 10 实测 GetString 对
        // BLOB 存储类做 UTF-8 替换解码**返回串**而非抛 InvalidCastException
        //（审计所称的逃逸向量在本驱动版本不可复现；InvalidCastException 防御
        // 仍保留为纵深——未来驱动行为收紧时兜底）。锁定可观察契约：损坏行
        // 绝不向启动恢复链抛异常（容忍/回退皆可，进程不可崩）。
        // BLOB 经参数绑定写入（TEXT 列亲和性不转换 BLOB——CAST 形态会被
        // 亲和性转回 TEXT，参数绑定才保持 BLOB 存储类）
        var store = new TabSessionStore(_dbPath);
        store.Save(
        [
            new("tab-a", "https://a.example", "A"),
            new("tab-b", "https://b.example", "B"),
        ], "tab-b");
        using (var connection = new Microsoft.Data.Sqlite.SqliteConnection(
            new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
            {
                DataSource = _dbPath,
                Pooling = false,
            }.ToString()))
        {
            connection.Open();
            using var cmd = connection.CreateCommand();
            cmd.CommandText = "UPDATE tabs SET url = $blob WHERE tab_id = 'tab-a'";
            cmd.Parameters.AddWithValue("$blob", new byte[] { 0xC3, 0x28, 0xFF, 0x00 });  // 非 UTF-8 序列 BLOB
            cmd.ExecuteNonQuery();
        }

        var ex = Record.Exception(() => store.Load());

        Assert.Null(ex);  // fail-safe：损坏行不阻断启动恢复
    }

    public void Dispose()
    {
        if (File.Exists(_dbPath))
            File.Delete(_dbPath);
    }
}

namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Microsoft.Data.Sqlite;
using Xunit;

/// <summary>M3 历史导入单测：临时 History 库（Chrome urls 表结构）→ 解析/
/// 过滤/计数。安全语义：仅 http/https、limit 上限、解析失败空结果。</summary>
public sealed class HistoryImporterTests : IDisposable
{
    private readonly string _tempDb = Path.Combine(
        Path.GetTempPath(), Path.GetRandomFileName());

    [Fact]
    public void ParseReadsRecentHttpHttpsEntries()
    {
        CreateFixtureDb(
            ("https://example.com/", "示例首页", 13370000010000000),
            ("https://example.com/page", "内页", 13370000020000000),
            ("javascript:void(0)", "坏条目", 13370000030000000));

        var candidates = HistoryImporter.Parse(_tempDb, limit: 10);

        Assert.Equal(2, candidates.Count);
        Assert.Equal("https://example.com/page", candidates[0].Url);  // 时间倒序
        Assert.Equal("内页", candidates[0].Title);
    }

    [Fact]
    public void ParseRespectsLimit()
    {
        for (var i = 0; i < 5; i++)
            CreateFixtureDb(($"https://example.com/{i}", $"页{i}", 13370000000000000 + i * 1000));

        Assert.Equal(3, HistoryImporter.Parse(_tempDb, limit: 3).Count);
    }

    [Fact]
    public void ParseFailureReturnsEmpty()
    {
        File.WriteAllText(_tempDb, "definitely not sqlite");

        Assert.Empty(HistoryImporter.Parse(_tempDb, 10));
        Assert.Empty(HistoryImporter.Parse(Path.Combine(Path.GetTempPath(), "missing.db"), 10));
    }

    [Fact]
    public void ImportToAppendsVisitsAndCountsAll()
    {
        var store = new HistoryStore(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));

        var (imported, total) = HistoryImporter.ImportTo(store,
        [
            new HistoryCandidate("A", "https://a.example"),
            new HistoryCandidate("B", "https://b.example"),
        ]);

        Assert.Equal(2, imported);
        Assert.Equal(2, total);
        Assert.Equal(2, store.Recent(10).Count);
    }

    [Fact]
    public void ImportToEmptyCandidatesReturnsZeroZero()
    {
        // CS-095：空候选导入返回 (0,0) 且不建脏数据
        var store = new HistoryStore(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));

        var (imported, total) = HistoryImporter.ImportTo(store, []);

        Assert.Equal(0, imported);
        Assert.Equal(0, total);
        Assert.Empty(store.Recent(10));
    }

    // ===== CS-399（2026-10-02 审计）：批量导入（单连接+事务+周期修剪） =====

    [Fact]
    public void ImportTo_WritesLargeBatchInSingleCall()
    {
        // 此前逐条 Add（每条新开 SQLite 连接）——批量接口一次写入全量
        var store = new HistoryStore(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
        var candidates = Enumerable.Range(0, 300)
            .Select(i => new HistoryCandidate($"页{i}", $"https://batch.example/{i}"))
            .ToList();

        var (imported, total) = HistoryImporter.ImportTo(store, candidates);

        Assert.Equal(300, imported);
        Assert.Equal(300, total);
        Assert.Equal(300, store.Recent(500).Count);
    }

    [Fact]
    public void ImportBatch_SkipsBlankUrls_AndCountsTotalSeparately()
    {
        // 空白 URL 跳过写入但计入解析总数（与既有 ImportTo 契约一致）
        var store = new HistoryStore(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));

        var (imported, total) = HistoryImporter.ImportTo(store,
        [
            new HistoryCandidate("A", "https://a.example"),
            new HistoryCandidate("B", "   "),
            new HistoryCandidate("", ""),
        ]);

        Assert.Equal(1, imported);
        Assert.Equal(3, total);
        Assert.Single(store.Recent(10));
    }

    [Fact]
    public void ImportBatch_BoundedByMaxRows_PeriodicPrune()
    {
        // 批内周期修剪（每 256 条同 Add 口径）+ 尾部收口——注入小阈值直测
        var store = new HistoryStore(
            Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()), maxRows: 10, pruneEveryAdds: 4);
        var candidates = Enumerable.Range(0, 30)
            .Select(i => new HistoryCandidate($"页{i}", $"https://prune.example/{i}"))
            .ToList();

        var imported = store.ImportBatch(candidates.Select(c => (c.Url, c.Title)));

        Assert.Equal(30, imported);          // 写入全部成功
        Assert.Equal(10, store.Recent(50).Count);  // 修剪后不超 maxRows
    }

    [Theory]
    [InlineData(0, 1)]       // CS-096：下界钳 1
    [InlineData(-5, 1)]
    [InlineData(1, 1)]
    [InlineData(1500, 1500)]
    [InlineData(2000, 2000)] // 上界恰值
    [InlineData(5000, 2000)] // 上界钳 2000
    public void ClampLimitBoundsParseLimit(int input, int expected) =>
        Assert.Equal(expected, HistoryImporter.ClampLimit(input));

    private void CreateFixtureDb(params (string Url, string Title, long LastVisit)[] rows)
    {
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = _tempDb,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = false,
        }.ToString());
        connection.Open();
        using var create = connection.CreateCommand();
        create.CommandText = """
            CREATE TABLE IF NOT EXISTS urls(
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                last_visit_time INTEGER NOT NULL DEFAULT 0)
            """;
        create.ExecuteNonQuery();
        foreach (var (url, title, lastVisit) in rows)
        {
            using var insert = connection.CreateCommand();
            insert.CommandText = "INSERT INTO urls(url, title, last_visit_time) VALUES($u,$t,$v)";
            insert.Parameters.AddWithValue("$u", url);
            insert.Parameters.AddWithValue("$t", title);
            insert.Parameters.AddWithValue("$v", lastVisit);
            insert.ExecuteNonQuery();
        }
    }

    public void Dispose()
    {
        try
        {
            File.Delete(_tempDb);
        }
        catch (IOException)
        {
            // 临时库清理失败不影响测试结果
        }
    }
}

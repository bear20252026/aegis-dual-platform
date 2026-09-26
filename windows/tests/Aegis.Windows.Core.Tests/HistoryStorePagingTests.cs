namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Xunit;

/// <summary>历史游标分页单测：跨页不重不漏、HasMore 边界、游标推进、筛选+游标组合。
/// 全部参数绑定（不拼接 SQL）。</summary>
public sealed class HistoryStorePagingTests
{
    [Fact]
    public void PagesOverAllEntriesWithoutDupOrSkip()
    {
        var store = NewStore();
        for (var i = 0; i < 250; i++)
            store.Add($"https://a.example/{i}", $"页{i}");

        var seen = new List<long>();
        PageCursor? cursor = null;
        var pages = 0;
        while (true)
        {
            var page = store.SearchRangePaged("", null, null, 100, cursor);
            foreach (var e in page.Entries)
                seen.Add(e.Id);
            pages++;
            if (!page.HasMore)
                break;
            Assert.NotNull(page.NextCursor);
            cursor = page.NextCursor;
        }

        Assert.Equal(250, seen.Count);
        Assert.Equal(3, pages);            // 100 + 100 + 50
        Assert.Equal(seen.Count, seen.Distinct().Count());  // 无重复
        Assert.Equal(250, store.Recent(1000).Count);         // 全部仍在库
    }

    [Fact]
    public void SinglePageWhenLessThanPageSize()
    {
        var store = NewStore();
        store.Add("https://a", "A");

        var page = store.SearchRangePaged("", null, null, 100, null);

        Assert.Single(page.Entries);
        Assert.False(page.HasMore);
        Assert.Null(page.NextCursor);
    }

    [Fact]
    public void FilteredPagingRespectsDateRangeAndCursor()
    {
        var store = NewStore();
        for (var i = 0; i < 20; i++)
            store.Add($"https://b.example/{i}", $"B{i}");

        var today = DateTime.Today.ToString("yyyy-MM-dd");
        var page1 = store.SearchRangePaged("", today, today, 5, null);
        Assert.Equal(5, page1.Entries.Count);
        Assert.True(page1.HasMore);

        var page2 = store.SearchRangePaged("", today, today, 5, page1.NextCursor);
        Assert.Equal(5, page2.Entries.Count);

        // 两页不重叠
        var ids = page1.Entries.Select(e => e.Id).Concat(page2.Entries.Select(e => e.Id)).ToList();
        Assert.Equal(ids.Count, ids.Distinct().Count());

        // 不匹配日期 → 空且无更多
        var none = store.SearchRangePaged("", "1999-01-01", "1999-01-01", 5, null);
        Assert.Empty(none.Entries);
        Assert.False(none.HasMore);
    }

    [Fact]
    public void TextFilterCombinesWithPaging()
    {
        var store = NewStore();
        for (var i = 0; i < 30; i++)
            store.Add($"https://c.example/{i}", $"目标{i}");
        store.Add("https://d.example", "无关页面");

        var page = store.SearchRangePaged("目标", null, null, 10, null);
        Assert.All(page.Entries, e => Assert.Contains("目标", e.Title));
        Assert.True(page.HasMore);
    }

    [Fact]
    public void RecentPagedMatchesSearchRangeEmpty()
    {
        var store = NewStore();
        for (var i = 0; i < 12; i++)
            store.Add($"https://e.example/{i}", $"E{i}");

        var viaSearch = store.SearchRangePaged("", null, null, 5, null);
        var viaRecent = store.RecentPaged(5, null);

        Assert.Equal(viaSearch.Entries.Select(e => e.Id),
            viaRecent.Entries.Select(e => e.Id));
    }

    [Fact]
    public void SingleEndedRangeCombinationsFilterCorrectly()
    {
        // CS-027：单端区间组合（仅 from / 仅 to）各自独立生效
        var store = NewStore();
        store.Add("https://a.example", "A");
        var today = DateTime.Now.ToString("yyyy-MM-dd");

        // 仅 from：未来下界 → 空；今天下界 → 命中
        Assert.Empty(store.SearchRangePaged("", "2099-01-01", null).Entries);
        Assert.Single(store.SearchRangePaged("", today, null).Entries);
        // 仅 to：过去上界 → 空；今天上界 → 命中
        Assert.Empty(store.SearchRangePaged("", null, "1999-01-01").Entries);
        Assert.Single(store.SearchRangePaged("", null, today).Entries);
        // 双端夹today → 命中
        Assert.Single(store.SearchRangePaged("", "1999-01-01", "2099-01-01").Entries);
    }

    [Fact]
    public void LastPageHasMoreIsFalse()
    {
        // CS-255：恰在末页（剩余数 ≤ pageSize）HasMore=false 且无下一页游标
        var store = NewStore();
        for (var i = 0; i < 7; i++)
            store.Add($"https://e.example/{i}", $"E{i}");

        var page = store.SearchRangePaged("", null, null, 5, null);
        Assert.Equal(5, page.Entries.Count);
        Assert.True(page.HasMore);
        Assert.NotNull(page.NextCursor);

        var lastPage = store.SearchRangePaged("", null, null, 5, page.NextCursor);
        Assert.Equal(2, lastPage.Entries.Count);
        Assert.False(lastPage.HasMore);
        Assert.Null(lastPage.NextCursor);
    }

    private static HistoryStore NewStore() =>
        new(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));

    // ===== C19b 批（审计 2026-09-26）：CS-301 同秒多条顺序锁定 =====

    /// <summary>绕过 Add 的时间戳生成直插指定 visited_at（强制同秒并列——
    /// Add 内部取 UtcNow 无法在单测内制造确定性并列）。</summary>
    private static void InsertRaw(string dbPath, string url, string visitedAt)
    {
        using var connection = new Microsoft.Data.Sqlite.SqliteConnection(
            new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
            {
                DataSource = dbPath,
                Mode = Microsoft.Data.Sqlite.SqliteOpenMode.ReadWriteCreate,
                Pooling = false,
            }.ToString());
        connection.Open();
        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO visits(url, title, visited_at, visited_date)
            VALUES($u, '', $v, '2026-09-26')
            """;
        insert.Parameters.AddWithValue("$u", url);
        insert.Parameters.AddWithValue("$v", visitedAt);
        insert.ExecuteNonQuery();
    }

    private static void NormalizeVisitedAt(string dbPath, string url, string visitedAt)
    {
        using var connection = new Microsoft.Data.Sqlite.SqliteConnection(
            new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
            {
                DataSource = dbPath,
                Mode = Microsoft.Data.Sqlite.SqliteOpenMode.ReadWriteCreate,
                Pooling = false,
            }.ToString());
        connection.Open();
        using var update = connection.CreateCommand();
        update.CommandText = "UPDATE visits SET visited_at = $v WHERE url = $u";
        update.Parameters.AddWithValue("$v", visitedAt);
        update.Parameters.AddWithValue("$u", url);
        update.ExecuteNonQuery();
    }

    [Fact]
    public void RecentAndSearch_TieBreakByIdDesc_MatchPagingOrder()
    {
        // CS-301：Recent/Search 此前仅 ORDER BY visited_at DESC（无 id 决胜），
        // 同一时刻多条记录时与分页查询（visited_at DESC, id DESC）顺序不一致。
        // 构造三条完全相同 visited_at 的记录（不同插入序→不同 id）
        var path = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
        var store = new HistoryStore(path);
        _ = store.Add("https://seed.example", "seed");  // 确保建表
        // seed 行归一到固定较早时刻——store.Add 用真实墙钟，UTC 午后运行时
        // seed 反而晚于 12:00Z 并列项，RecentPage 断言随时钟漂移。
        const string seedInstant = "2026-09-26T11:00:00.0000000Z";
        NormalizeVisitedAt(path, "https://seed.example", seedInstant);
        const string sameInstant = "2026-09-26T12:00:00.0000000Z";
        InsertRaw(path, "https://tie.example/a", sameInstant);
        InsertRaw(path, "https://tie.example/b", sameInstant);
        InsertRaw(path, "https://tie.example/c", sameInstant);

        var ties = store.Recent(10)
            .Where(e => e.Url.StartsWith("https://tie.example", StringComparison.Ordinal)).ToList();
        Assert.Equal(3, ties.Count);
        // 决胜列：同 visited_at 内按 id 倒序（最新插入在前）
        Assert.Equal("https://tie.example/c", ties[0].Url);
        Assert.Equal("https://tie.example/b", ties[1].Url);
        Assert.Equal("https://tie.example/a", ties[2].Url);

        // 与分页口径一致（不重复跳行）
        var paged = store.RecentPage(2, 0).Select(e => e.Url).ToList();
        Assert.Equal(ties.Take(2).Select(e => e.Url), paged);

        // Search 同口径（子串命中全部并列项）
        var searched = store.Search("tie.example")
            .Where(e => e.Url.StartsWith("https://tie.example", StringComparison.Ordinal)).ToList();
        Assert.Equal(ties.Select(e => e.Url), searched.Select(e => e.Url));
    }

    [Fact]
    public void Add_ClampsUrlAndTitle_StoreLayerBoundaries()
    {
        // CS-319：库层统一钳制——手写路径（Star_Click 直 Add）此前可写入
        // 任意长串（BookmarkImporter 有 2048/256 上限，双口径）；截断代理对安全
        var path = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
        var store = new HistoryStore(path);
        var longUrl = "https://clip.example/" + new string('u', 3000);
        // 255 个 a + emoji（高代理恰在 256 截断点上）+ 尾巴 → 回退一位不劈半
        var longTitle = new string('a', 255) + "\U0001F600" + new string('b', 100);

        Assert.True(store.Add(longUrl, longTitle));
        var entry = Assert.Single(store.Recent(10));

        Assert.Equal(HistoryStore.MaxUrlChars, entry.Url.Length);
        Assert.Equal(255, entry.Title.Length);  // 256 处高代理回退一位
        Assert.All(entry.Title, c => Assert.False(char.IsSurrogate(c)));
    }

    [Fact]
    public void ClampText_SurrogateSafeBoundaries()
    {
        // CS-319 提纯直测：未超长原样；高代理边界回退；低代理边界不回退
        var text = new string('a', 10) + "\U0001F600bc";
        Assert.Equal(text, HistoryStore.ClampText(text, 50));
        Assert.Equal(new string('a', 10), HistoryStore.ClampText(text, 11));
        Assert.Equal(new string('a', 10) + "\U0001F600", HistoryStore.ClampText(text, 12));
    }
}
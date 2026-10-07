namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Xunit;

/// <summary>历史查询的顺序与钳制不变量单测：同秒并列项按 id 倒序、`Recent` 与
/// offset 分页（<c>RecentPage</c>）口径一致、URL/标题写入钳制的库层边界、代理对安全截断。
/// 全部参数绑定（不拼接 SQL）。
///
/// ⑥（第八轮 2026-10-07）：本文件原有 7 例是 **keyset 游标分页**
///（`SearchRangePaged`/`RecentPaged`/`PageCursor`/`HasMore`）的断言——那两个方法是
/// 零生产调用方的死面（生产分页走 `SearchRangePage` 的 OFFSET 口径），随方法一并删除。
/// 两套并存的键集分页不是"未被使用的资产"，而是"未有人验证过的第二套排序口径"：
/// 它自己的 <c>TieBreak</c> 用例正好需要拿 <c>Recent</c> 与 <c>RecentPage</c> 对齐才成立，
/// 说明一致性本该由单源保证而不是靠第二套实现互相盖章。</summary>
public sealed class HistoryStorePagingTests
{
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
    public void RecentAndSearchByUrl_TieBreakByIdDesc_MatchPagingOrder()
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

        // SearchByUrl（生产在用的查询面）同口径：子串命中全部并列项
        var searched = store.SearchByUrl("tie.example")
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
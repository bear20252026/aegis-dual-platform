namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Microsoft.Data.Sqlite;
using Xunit;

/// <summary>历史库存储层不变量单测（写入归一日期、参数绑定、旧 schema 迁移补列、
/// 删除与 limit 钳制）。⑥（第八轮）把观测口径从零调用方的查询面（Search/ByDate/Dates，
/// 已删）移到生产真正在用的 Recent / SearchByUrl / SearchRangePage。</summary>
public sealed class HistoryStoreUpgradeTests
{
    [Fact]
    public void AddRecordsLocalDateAndTime()
    {
        var store = NewStore();
        store.Add("https://a.example/x", "A页");

        var today = DateTime.Now.ToString("yyyy-MM-dd");
        var rows = store.Recent(50)
            .Where(e => e.VisitedDate == today).ToList();

        Assert.Single(rows);
        Assert.Equal("https://a.example/x", rows[0].Url);
        Assert.Equal("A页", rows[0].Title);
        Assert.Equal(today, rows[0].VisitedDate);
        Assert.Contains("T", rows[0].VisitedAt);  // ISO 含时刻
    }
    [Fact]
    public void SearchWithDateFiltersToThatDay()
    {
        var store = NewStore();
        store.Add("https://a.example/one", "首项");
        store.Add("https://a.example/two", "次项");

        var today = DateTime.Now.ToString("yyyy-MM-dd");
        // 文本命中 + 日期命中（观测口径改走生产在用的 SearchRangePage/Count：
        // 原断言走的 Search 是零调用方的死面，标题列匹配随之一并退出——
        // 「历史仅 URL 命中」的口径本就由 CS-401 定在 SearchByUrl 侧）
        Assert.Equal(2, store.SearchRangePage("example", today, today, 50, 0).Count);
        Assert.Equal(2, store.Count("example", today, today));
        // 文本命中但日期不匹配 → 空（CS-021：未知日期空结果，不抛）
        Assert.Empty(store.SearchRangePage("example", "1999-01-01", "1999-01-01", 50, 0));
        Assert.Equal(0, store.Count("example", "1999-01-01", "1999-01-01"));
    }

    [Fact]
    public void DeleteRemovesSingleRow()
    {
        var store = NewStore();
        store.Add("https://a.example", "A");
        store.Add("https://b.example", "B");

        var all = store.Recent(50);
        var target = all.First(x => x.Url == "https://a.example");

        Assert.True(store.Delete(target.Id));
        var after = store.Recent(50);

        Assert.Single(after);
        Assert.Equal("https://b.example", after[0].Url);
    }

    [Fact]
    public void MigrateBackfillsVisitedDateOnOldSchema()
    {
        // 模拟旧库：无 visited_date 列 + 已有一行 ISO 时间——Open() 迁移应补列并回填
        var path = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
        try
        {
            using (var conn = new SqliteConnection(new SqliteConnectionStringBuilder
                   {
                       DataSource = path,
                       Mode = SqliteOpenMode.ReadWriteCreate,
                       Pooling = false,
                   }.ToString()))
            {
                conn.Open();
                using var create = conn.CreateCommand();
                create.CommandText = "CREATE TABLE visits(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', visited_at TEXT NOT NULL)";
                create.ExecuteNonQuery();
                using var ins = conn.CreateCommand();
                ins.CommandText = "INSERT INTO visits(url, title, visited_at) VALUES($u,$t,$v)";
                ins.Parameters.AddWithValue("$u", "https://old.example");
                ins.Parameters.AddWithValue("$t", "旧页");
                ins.Parameters.AddWithValue("$v", DateTime.Now.ToString("o"));
                ins.ExecuteNonQuery();
            }

            var store = new HistoryStore(path);
            var today = DateTime.Now.ToString("yyyy-MM-dd");
            var rows = store.Recent(50)
            .Where(e => e.VisitedDate == today).ToList();

            Assert.Single(rows);
            Assert.Equal(today, rows[0].VisitedDate);
        }
        finally
        {
            try { File.Delete(path); }
            catch (IOException) { /* 清理失败不影响 */ }
        }
    }
    [Fact]
    public void LimitClampsAndBounds()
    {
        // CS-022：limit 边界——0/负值不得触发 SQLite 的「负 LIMIT = 无上限」语义
        //（CS-028 钳制后 limit<=0 等价 1）。观测口径改走生产在用的 Recent：
        // 原断言的 Dates 是零调用方死面，钳制逻辑同为 ClampLimit 单源。
        var store = NewStore();
        store.Add("https://a.example", "A");
        Assert.Single(store.Recent(0));
        Assert.Single(store.Recent(-5));
        Assert.Single(store.Recent(90));
    }

    [Fact]
    public void DeleteUnknownIdReturnsFalse()
    {
        // CS-023：删除不存在的 id 返回 false
        var store = NewStore();
        store.Add("https://a.example", "A");
        Assert.False(store.Delete(999_999));
        Assert.True(store.Delete(store.Recent(10)[0].Id));
    }

    private static HistoryStore NewStore() =>
        new(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
}

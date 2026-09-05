namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Microsoft.Data.Sqlite;
using Xunit;

/// <summary>历史升级（按日期查询/日期列表/单条删除/迁移补列）单测——
/// 验证全部参数绑定路径与按日期分组查询语义。</summary>
public sealed class HistoryStoreUpgradeTests
{
    [Fact]
    public void AddRecordsLocalDateAndTime()
    {
        var store = NewStore();
        store.Add("https://a.example/x", "A页");

        var today = DateTime.Now.ToString("yyyy-MM-dd");
        var rows = store.ByDate(today, 50);

        Assert.Single(rows);
        Assert.Equal("https://a.example/x", rows[0].Url);
        Assert.Equal("A页", rows[0].Title);
        Assert.Equal(today, rows[0].VisitedDate);
        Assert.Contains("T", rows[0].VisitedAt);  // ISO 含时刻
    }

    [Fact]
    public void ByDateOnlyReturnsThatDay()
    {
        var store = NewStore();
        store.Add("https://a.example", "A");
        store.Add("https://b.example", "B");

        var today = DateTime.Now.ToString("yyyy-MM-dd");
        var rows = store.ByDate(today, 50);

        Assert.Equal(2, rows.Count);
        // 构造一个绝不存在的日期 → 空
        Assert.Empty(store.ByDate("1999-01-01", 50));
    }

    [Fact]
    public void DatesListsDistinctRecentDays()
    {
        var store = NewStore();
        store.Add("https://a.example", "A");
        store.Add("https://b.example", "B");

        var today = DateTime.Now.ToString("yyyy-MM-dd");
        var dates = store.Dates(90);

        Assert.Contains(today, dates);
        Assert.Equal(dates.Count, dates.Distinct().Count());
    }

    [Fact]
    public void SearchWithDateFiltersToThatDay()
    {
        var store = NewStore();
        store.Add("https://a.example/one", "首项");
        store.Add("https://a.example/two", "次项");

        var today = DateTime.Now.ToString("yyyy-MM-dd");
        // 文本命中 + 日期命中
        Assert.Equal(2, store.Search("example", today, 50).Count);
        Assert.Single(store.Search("首项", today, 50));
        // 文本命中但日期不匹配 → 空
        Assert.Empty(store.Search("example", "1999-01-01", 50));
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
            var rows = store.ByDate(today, 50);

            Assert.Single(rows);
            Assert.Equal(today, rows[0].VisitedDate);
        }
        finally
        {
            try { File.Delete(path); }
            catch (IOException) { /* 清理失败不影响 */ }
        }
    }

    private static HistoryStore NewStore() =>
        new(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
}

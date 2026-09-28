namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using System.Globalization;
using Xunit;

/// <summary>C8 批（审计 2026-09-26）：历史库保留修剪/时间口径/LIKE 转义单测。
/// 修剪常态阈值 50k 行、每 256 次触发——离线不可测；经 internal 构造器注入
/// 小阈值直测（CS-084）。时间口径：visited_at 为 UTC round-trip（CS-090——
/// 本地时字符串在 DST 回拨时段字典序错乱），visited_date 仍为本地日不变。</summary>
public sealed class HistoryStoreRetentionTests : IDisposable
{
    private readonly string _dbPath =
        Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());

    [Fact]
    public void PruneKeepsNewestRowsWithinCap()
    {
        // CS-084：每次添加即修剪（阈值注入 3/1）——7 条后仅存最新 3 条
        var store = new HistoryStore(_dbPath, maxRows: 3, pruneEveryAdds: 1);
        for (var i = 1; i <= 7; i++)
            store.Add($"https://example.com/{i}", $"页{i}");

        var recent = store.Recent(50);
        Assert.Equal(3, recent.Count);
        Assert.Equal(
            new HashSet<string> { "https://example.com/5", "https://example.com/6", "https://example.com/7" },
            recent.Select(e => e.Url).ToHashSet());
    }

    [Fact]
    public void PruneDeferredUntilTriggerPoint()
    {
        // CS-084 伴断言：未到触发点不修剪——3 条超 2 条上限但全保留
        var store = new HistoryStore(_dbPath, maxRows: 2, pruneEveryAdds: 4);
        for (var i = 1; i <= 3; i++)
            store.Add($"https://example.com/{i}", $"页{i}");

        Assert.Equal(3, store.Recent(50).Count);
    }

    [Fact]
    public void VisitedAtStoredAsUtcRoundTrip()
    {
        // CS-090：visited_at 为 UTC ISO round-trip（Z 后缀），可精确还原时刻
        var store = new HistoryStore(_dbPath);
        Assert.True(store.Add("https://example.com/", "标题"));

        var entry = store.Recent(1)[0];
        Assert.EndsWith("Z", entry.VisitedAt);
        var parsed = DateTimeOffset.ParseExact(
            entry.VisitedAt, "o", CultureInfo.InvariantCulture);
        Assert.Equal(DateTimeOffset.UtcNow, parsed, TimeSpan.FromMinutes(1));
    }

    [Fact]
    public void VisitedDateIsInvariantLocalCalendarDay()
    {
        // CS-089：本地日按 InvariantCulture 公历格式化（默认日历文化不漂移）
        var store = new HistoryStore(_dbPath);
        store.Add("https://example.com/", "标题");

        var entry = store.Recent(1)[0];
        var expected = DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        Assert.Equal(expected, entry.VisitedDate);
    }

    public void Dispose()
    {
        try
        {
            if (File.Exists(_dbPath))
                File.Delete(_dbPath);
        }
        catch (IOException)
        {
            // 临时库清理失败不影响测试结果
        }
    }
}

/// <summary>CS-092：LIKE 转义单遍实现的行为锁定——%/_/字面量语义与
/// 三连 Replace 版本一致。</summary>
public sealed class HistoryFilterTests : IDisposable
{
    private readonly string _dbPath =
        Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());

    [Theory]
    [InlineData("100%", "100\\%")]
    [InlineData("a_b", "a\\_b")]
    [InlineData("a\\b", "a\\\\b")]
    [InlineData("%_\\", "\\%\\_\\\\")]
    [InlineData("普通文本", "普通文本")]
    [InlineData("", "")]
    public void LikeEscapeEscapesOnlyWildcards(string input, string expected) =>
        Assert.Equal(expected, HistoryFilter.LikeEscape(input));

    [Fact]
    public void SearchTreatsLikeWildcardsAsLiterals()
    {
        var store = new HistoryStore(_dbPath);
        store.Add("https://example.com/100%.html", "百分号页");
        store.Add("https://example.com/100x.html", "普通页");

        var hits = store.Search("100%");

        Assert.Single(hits);
        Assert.Contains("100%.html", hits[0].Url);
    }

    public void Dispose()
    {
        try
        {
            if (File.Exists(_dbPath))
                File.Delete(_dbPath);
        }
        catch (IOException)
        {
            // 临时库清理失败不影响测试结果
        }
    }
}

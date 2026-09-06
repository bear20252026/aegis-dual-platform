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

    private static HistoryStore NewStore() =>
        new(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
}
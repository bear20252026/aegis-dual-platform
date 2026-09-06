namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Xunit;

/// <summary>页码分页（COUNT + LIMIT/OFFSET）回归测试：页大小、总页数、跳页与筛选。</summary>
public sealed class HistoryStorePageNumberTests
{
    [Fact]
    public void CountAndOffsetPagesCoverAllRows()
    {
        var store = NewStore();
        for (var i = 0; i < 235; i++)
            store.Add($"https://page.example/{i}", $"页面{i}");

        var total = store.Count(null, null, null);
        var page1 = store.SearchRangePage(null, null, null, 100, 0);
        var page2 = store.SearchRangePage(null, null, null, 100, 100);
        var page3 = store.SearchRangePage(null, null, null, 100, 200);
        var page4 = store.SearchRangePage(null, null, null, 100, 300);

        Assert.Equal(235, total);
        Assert.Equal(100, page1.Count);
        Assert.Equal(100, page2.Count);
        Assert.Equal(35, page3.Count);
        Assert.Empty(page4);
        var ids = page1.Concat(page2).Concat(page3).Select(x => x.Id).ToList();
        Assert.Equal(235, ids.Distinct().Count());
    }

    [Fact]
    public void OffsetPageRespectsTextAndDateFilters()
    {
        var store = NewStore();
        for (var i = 0; i < 12; i++)
            store.Add($"https://match.example/{i}", "命中");
        store.Add("https://other.example", "其他页面");
        var today = DateTime.Now.ToString("yyyy-MM-dd");

        Assert.Equal(12, store.Count("命中", today, today));
        Assert.Equal(5, store.SearchRangePage("命中", today, today, 5, 5).Count);
        Assert.Empty(store.SearchRangePage("命中", "1999-01-01", "1999-01-01", 5, 0));
    }

    private static HistoryStore NewStore() =>
        new(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
}

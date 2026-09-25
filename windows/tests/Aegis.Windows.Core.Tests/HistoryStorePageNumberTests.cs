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

    [Fact]
    public void TitleOnlyHitCountsAndWildcardEscapeHolds()
    {
        // CS-026 + CS-018 回归：仅标题命中的行计入 Count；标题中的 %/_
        // 作为字面量匹配（不再当通配符改变搜索语义）
        var store = NewStore();
        store.Add("https://plain.example", "普通页");
        store.Add("https://pct.example", "a_b 百分之百%折扣");

        // 仅标题命中
        Assert.Equal(1, store.Count("普通页", null, null));
        // %/_ 字面量：精确命中原文
        Assert.Equal(1, store.Count("a_b", null, null));
        Assert.Equal(1, store.Count("百%折扣", null, null));
        // 若 %/_ 仍当通配，这些"不可能串"会误命中——锁定为 0
        Assert.Equal(0, store.Count("aXb", null, null));
        Assert.Equal(0, store.Count("百分之X百%折扣", null, null));
    }

    private static HistoryStore NewStore() =>
        new(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
}

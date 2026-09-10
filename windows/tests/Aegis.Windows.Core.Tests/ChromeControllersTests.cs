namespace Aegis.Windows.Core.Tests;

using System.Collections.Generic;
using Aegis.Windows.Chrome;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.History;
using Xunit;

/// <summary>MainWindow 拆分第一批（查找条/建议控制器）的纯逻辑单测：
/// 建议 合并去重/上限/空标题回退 与 window.find 脚本转义/方向参数。</summary>
public sealed class ChromeControllersTests
{
    private static Bookmark Bm(string title, string url) => new(0, title, url);
    private static HistoryEntry He(string title, string url) => new(0, url, title, "2026-09-10 10:00:00", "2026-09-10");

    [Fact]
    public void MergeRows_MatchesCaseInsensitive_AndDedupsByUrl_BookmarkFirst()
    {
        // 去重按完整 URL：书签与历史同 URL 时只保留书签行
        var rows = SuggestionController.MergeRows(
            "EXAMPLE",
            new[] { Bm("示例站", "https://example.com/"), Bm("其它", "https://other.com/") },
            new[] { He("Example 历史", "https://example.com/") },
            maxRows: 8);
        var row = Assert.Single(rows);
        Assert.Equal("https://example.com/", row.Url);
        Assert.Equal("书签", row.Kind);
    }

    [Fact]
    public void MergeRows_HistoryMatchesByUrlOnly_TitleNeverMatches()
    {
        // 既有口径：书签匹配标题或 URL，历史仅匹配 URL——标题不含查询词的历史
        // 行不出现（固化行为，防回归时误"修复"）
        var rows = SuggestionController.MergeRows(
            "query", new Bookmark[0], new[] { He("query in title", "https://h.test/no-match") }, 8);
        Assert.Empty(rows);
    }

    [Fact]
    public void MergeRows_FallsBackToUrl_WhenTitleBlank()
    {
        var rows = SuggestionController.MergeRows(
            "target", new[] { Bm("", "https://a.test/target") }, new HistoryEntry[0], 8);
        var row = Assert.Single(rows);
        Assert.Equal("https://a.test/target", row.Title);
    }

    [Fact]
    public void MergeRows_CapsAtMaxRows_BookmarksTakePriority()
    {
        var bookmarks = new List<Bookmark>();
        for (var i = 0; i < 6; i++)
            bookmarks.Add(Bm($"hit{i}", $"https://hit.test/{i}"));
        var history = new List<HistoryEntry>();
        for (var i = 0; i < 10; i++)
            history.Add(He($"hit{i}", $"https://hit-history.test/{i}"));
        var rows = SuggestionController.MergeRows("hit", bookmarks, history, maxRows: 8);
        Assert.Equal(8, rows.Count);
        // 前 6 条为书签（优先），后 2 条为历史
        Assert.Equal(6, rows.Count(r => r.Kind == "书签"));
        Assert.Equal(2, rows.Count(r => r.Kind == "历史"));
    }

    [Fact]
    public void MergeRows_EmptyQueryMatchesEverything_StillDeduped()
    {
        var rows = SuggestionController.MergeRows(
            "", new[] { Bm("a", "https://same.test/"), Bm("dup", "https://same.test/") },
            new[] { He("h", "https://same.test/") }, 8);
        var row = Assert.Single(rows);
        Assert.Equal("书签", row.Kind);
    }

    [Fact]
    public void BuildFindJs_EscapesQuotesAndEncodesDirection()
    {
        // System.Text.Json 默认编码器把 " 转为 \u0022（JS 合法等价转义）
        var forward = FindBarController.BuildFindJs("a\"b\\c", backwards: false);
        Assert.StartsWith("window.find(\"a\\u0022b\\\\c\", false, false, true);", forward);
        var backward = FindBarController.BuildFindJs("x", backwards: true);
        Assert.Contains(", false, true, true);", backward);
    }

    [Fact]
    public void BuildCountJs_EscapesQuery_ResolvedPromiseShape()
    {
        var js = FindBarController.BuildCountJs("q\"q");
        Assert.StartsWith("new Promise(r=>{try{var m=(document.body&&document.body.innerText)||'';", js);
        Assert.Contains("Q=\"q\\u0022q\";", js);
        Assert.EndsWith("r(n);}catch(e){r(0);}});", js);
    }

    [Fact]
    public void FilterSources_NullOrAll_ReturnsAll()
    {
        var sources = new[] { ("chrome", 1), ("edge", 2) };
        Assert.Equal(2, NtpBridgeFactory.FilterSources(sources, null, s => s.Item1).Count());
        Assert.Equal(2, NtpBridgeFactory.FilterSources(sources, "all", s => s.Item1).Count());
        Assert.Equal(2, NtpBridgeFactory.FilterSources(sources, "", s => s.Item1).Count());
    }

    [Fact]
    public void FilterSources_NamedBrowser_ReturnsOnlyThatBrowser()
    {
        var sources = new[] { ("chrome", 1), ("edge", 2), ("chrome", 3) };
        var filtered = NtpBridgeFactory.FilterSources(sources, "chrome", s => s.Item1).ToList();
        Assert.Equal(new[] { 1, 3 }, filtered.Select(s => s.Item2));
    }
}

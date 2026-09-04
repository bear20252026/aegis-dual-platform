namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Bookmarks;
using Xunit;

/// <summary>M2（ADR-009）：书签存储与导入单测。</summary>
public sealed class BookmarkStoreTests : IDisposable
{
    private readonly string _dbPath =
        Path.Combine(Path.GetTempPath(), $"aegis_bm_{Guid.NewGuid():N}.db");
    private readonly BookmarkStore _store;

    public BookmarkStoreTests() => _store = new BookmarkStore(_dbPath);

    [Fact]
    public void AddThenContainsThenRemove()
    {
        Assert.True(_store.Add("示例", "https://example.com"));
        Assert.True(_store.Contains("https://example.com"));
        Assert.True(_store.Remove("https://example.com"));
        Assert.False(_store.Contains("https://example.com"));
    }

    [Fact]
    public void DuplicateUrlIsIdempotent()
    {
        Assert.True(_store.Add("第一次", "https://example.com"));
        Assert.False(_store.Add("第二次", "https://example.com"));
        var all = _store.All();
        Assert.Single(all);
        Assert.Equal("第一次", all[0].Title);  // 首次写入保留
    }

    [Fact]
    public void BlankUrlRejected()
    {
        Assert.False(_store.Add("空", ""));
        Assert.False(_store.Add("空白", "   "));
    }

    [Fact]
    public void AllPreservesInsertOrder()
    {
        _store.Add("甲", "https://jia.cn");
        _store.Add("乙", "https://yi.cn");
        var all = _store.All();
        Assert.Equal(["https://jia.cn", "https://yi.cn"], all.Select(b => b.Url));
    }

    [Fact]
    public void RemoveNonexistentReturnsFalse()
    {
        Assert.False(_store.Remove("https://nothing.example"));
    }

    public void Dispose()
    {
        if (File.Exists(_dbPath))
            File.Delete(_dbPath);
    }
}

/// <summary>书签导入（Chrome/Edge Bookmarks JSON 解析）单测。</summary>
public sealed class BookmarkImporterTests : IDisposable
{
    private readonly string _jsonPath =
        Path.Combine(Path.GetTempPath(), $"aegis_bm_json_{Guid.NewGuid():N}.json");

    [Fact]
    public void ParseFiltersNonHttpAndWalksChildren()
    {
        var payload = """
            {"roots":{"bookmark_bar":{"type":"folder","children":[
                {"type":"url","name":"站点甲","url":"https://jia.cn"},
                {"type":"url","name":"坏协议","url":"javascript:void(0)"},
                {"type":"folder","name":"子文件夹","children":[
                    {"type":"url","name":"嵌套","url":"https://nested.cn/x"}
                ]}
            ]},"other":{"type":"folder","children":[
                {"type":"url","name":"站点乙","url":"http://yi.cn/x?a=1"}
            ]},"synced":null}}
            """;
        File.WriteAllText(_jsonPath, payload);

        var candidates = BookmarkImporter.Parse(_jsonPath);

        Assert.Equal(3, candidates.Count);  // javascript: 被滤
        Assert.Contains(candidates, c => c.Url == "https://nested.cn/x");
        Assert.Contains(candidates, c => c.Title == "站点甲");
    }

    [Fact]
    public void ImportToDeduplicates()
    {
        var store = new BookmarkStore(Path.Combine(Path.GetTempPath(), $"aegis_bm2_{Guid.NewGuid():N}.db"));
        var candidates = new List<BookmarkCandidate>
        {
            new("甲", "https://jia.cn"),
            new("甲重复", "https://jia.cn"),
        };

        var (imported, total) = BookmarkImporter.ImportTo(store, candidates);

        Assert.Equal(1, imported);
        Assert.Equal(2, total);
        Assert.True(store.Contains("https://jia.cn"));
        store.Remove("https://jia.cn");
        File.Delete(store.ToString());  // no-op 清理（db 路径独立）
    }

    public void Dispose()
    {
        if (File.Exists(_jsonPath))
            File.Delete(_jsonPath);
    }
}

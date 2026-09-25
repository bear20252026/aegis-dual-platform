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

    // ===== CS-046..050（审计 2026-09-25）：书签管理路径零覆盖补齐 =====

    [Fact]
    public void RenameExistingBookmarkUpdatesTitle()
    {
        // CS-046：Rename 正路径
        _store.Add("旧标题", "https://example.com");
        var id = _store.All()[0].Id;

        Assert.True(_store.Rename(id, "新标题"));
        Assert.Equal("新标题", _store.All()[0].Title);
    }

    [Fact]
    public void RenameWithBlankTitleReturnsFalse()
    {
        // CS-047：空白标题拒绝（不做无意义 UPDATE）
        _store.Add("标题", "https://example.com");
        var id = _store.All()[0].Id;

        Assert.False(_store.Rename(id, ""));
        Assert.False(_store.Rename(id, "   "));
        Assert.False(_store.Rename(id, null!));
        Assert.Equal("标题", _store.All()[0].Title);
    }

    [Fact]
    public void RemoveByIdUnknownReturnsFalse()
    {
        // CS-048：不存在的 id 返回 false
        _store.Add("标题", "https://example.com");
        Assert.False(_store.RemoveById(999_999));
        Assert.True(_store.RemoveById(_store.All()[0].Id));
    }

    [Fact]
    public void ClearAllRemovesEverything()
    {
        // CS-049：ClearAll 后全空
        _store.Add("甲", "https://jia.cn");
        _store.Add("乙", "https://yi.cn");

        _store.ClearAll();

        Assert.Empty(_store.All());
    }

    [Fact]
    public void ImportCountsTotalIncludingDuplicates()
    {
        // CS-050：重复 URL 计入 total 但不计入 imported（INSERT OR IGNORE 语义）
        _store.Add("已存在", "https://example.com");

        var (imported, total) = _store.Import(new[]
        {
            ("新站一", "https://one.example"),
            ("重复", "https://example.com"),   // 重复——total 计、imported 不计
            ("空白", "   "),                    // 非法——两者都不计
        });

        Assert.Equal(2, total);
        Assert.Equal(1, imported);
        Assert.Equal(2, _store.All().Count);
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

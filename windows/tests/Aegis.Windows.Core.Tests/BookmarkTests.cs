namespace Aegis.Windows.Core.Tests;

using System.Text;
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

    // ===== CS-097/098（审计 2026-09-26）：空白候选与空白标题边界 =====

    [Fact]
    public void AddWithBlankTitleReturnsFalse()
    {
        // CS-098：空白标题拒绝且不落库
        Assert.False(_store.Add("", "https://example.com"));
        Assert.False(_store.Add("   ", "https://example.com"));
        Assert.False(_store.Add(null!, "https://example.com"));
        Assert.Empty(_store.All());
    }

    [Fact]
    public void ImportSkipsBlankCandidatesFromTotal()
    {
        // CS-097：空白候选在导入层被跳过且不计入 total（区别于重复——重复计 total）
        var (imported, total) = BookmarkImporter.ImportTo(_store,
        [
            new BookmarkCandidate("正常", "https://ok.example"),
            new BookmarkCandidate("空URL", "   "),
            new BookmarkCandidate("", "https://blank-title.example"),
        ]);

        Assert.Equal(1, imported);
        Assert.Equal(1, total);
        Assert.Single(_store.All());
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

    // ===== CS-100..105（审计 2026-09-26）：解析容错与边界 =====

    [Fact]
    public void MalformedJsonOrMissingFileReturnsEmpty()
    {
        // CS-100：损坏 JSON/缺失文件不再上抛——可选功能 fail-safe 返回空
        File.WriteAllText(_jsonPath, "{not json at all");
        Assert.Empty(BookmarkImporter.Parse(_jsonPath));
        Assert.Empty(BookmarkImporter.Parse(
            Path.Combine(Path.GetTempPath(), "missing_bookmarks.json")));
    }

    [Fact]
    public void TrimTitleNeverSplitsSurrogatePair()
    {
        // CS-101：截断边界恰落在代理对上时回退一位，不产生孤立代理
        var emoji = "\U0001F600";  // 😀——UTF-16 代理对（2 char）
        Assert.Equal(new string('a', 255), BookmarkImporter.TrimTitle(new string('a', 255) + emoji));
        Assert.Equal(new string('b', 256), BookmarkImporter.TrimTitle(new string('b', 256) + emoji));
        Assert.Equal("短标题", BookmarkImporter.TrimTitle("短标题"));
    }

    [Fact]
    public void DeepNestingBeyondBoundIsBounded()
    {
        // CS-102：200 层嵌套文件夹——深度有界（Walk 64 层 + JsonDocument 解析
        // 上限双保险），返回空而非栈溢出/无限递归
        var builder = new StringBuilder();
        builder.Append("{\"roots\":{\"bookmark_bar\":");
        for (var i = 0; i < 200; i++)
            builder.Append("{\"type\":\"folder\",\"children\":[");
        builder.Append("{\"type\":\"url\",\"name\":\"深巢\",\"url\":\"https://deep.example\"}");
        for (var i = 0; i < 200; i++)
            builder.Append("]}");
        builder.Append("}}");  // 仅剩 roots 与根两对象待闭（bookmark_bar 值即首层 folder）
        File.WriteAllText(_jsonPath, builder.ToString());

        Assert.Empty(BookmarkImporter.Parse(_jsonPath));
    }

    [Fact]
    public void NestingWithinBoundStillImports()
    {
        // CS-102 正路径：界内嵌套正常导入
        var builder = new StringBuilder();
        builder.Append("{\"roots\":{\"bookmark_bar\":");
        for (var i = 0; i < 10; i++)
            builder.Append("{\"type\":\"folder\",\"children\":[");
        builder.Append("{\"type\":\"url\",\"name\":\"十层\",\"url\":\"https://ok.example\"}");
        for (var i = 0; i < 10; i++)
            builder.Append("]}");
        builder.Append("}}");  // 仅剩 roots 与根两对象待闭
        File.WriteAllText(_jsonPath, builder.ToString());

        Assert.Single(BookmarkImporter.Parse(_jsonPath));
    }

    [Fact]
    public void MissingRootsKeyReturnsEmpty()
    {
        // CS-103：无 roots 键返回空列表
        File.WriteAllText(_jsonPath, "{\"bookmark_bar\":{\"type\":\"folder\"}}");
        Assert.Empty(BookmarkImporter.Parse(_jsonPath));
    }

    [Fact]
    public void OversizedUrlRejected()
    {
        // CS-104：URL 超 2048 拒收
        var payload = "{\"roots\":{\"bookmark_bar\":{\"type\":\"url\",\"name\":\"超长\"," +
                      "\"url\":\"https://example.com/" + new string('a', 2100) + "\"}}}";
        File.WriteAllText(_jsonPath, payload);

        Assert.Empty(BookmarkImporter.Parse(_jsonPath));
    }

    [Fact]
    public void MissingNameFallsBackToHost()
    {
        // CS-105：name 缺省回退 host（对齐 Python `name or host`——此前整条丢弃）
        var payload = "{\"roots\":{\"bookmark_bar\":{\"type\":\"url\"," +
                      "\"url\":\"https://fallback.example/x\"}}}";
        File.WriteAllText(_jsonPath, payload);

        var candidates = BookmarkImporter.Parse(_jsonPath);
        Assert.Single(candidates);
        Assert.Equal("fallback.example", candidates[0].Title);
        Assert.Equal("https://fallback.example/x", candidates[0].Url);
    }

    public void Dispose()
    {
        if (File.Exists(_jsonPath))
            File.Delete(_jsonPath);
    }
}

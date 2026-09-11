namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using System.Linq;
using Aegis.Windows.Core.Downloads;
using Xunit;

/// <summary>下载记录持久化单测（测试缺口批次 2）：新增/倒序读取/null 字段防御、
/// 有界保留 500 条修剪最旧、Clear 全清、limit 参数。</summary>
public sealed class DownloadRecordStoreTests : IDisposable
{
    private readonly string _dbPath =
        Path.Combine(Path.GetTempPath(), $"aegis_dl_{Guid.NewGuid():N}.db");

    private readonly DownloadRecordStore _store;

    public DownloadRecordStoreTests() => _store = new DownloadRecordStore(_dbPath);

    [Fact]
    public void Add_PersistsAndReadsNewestFirst()
    {
        _store.Add("a.zip", @"C:\x\a.zip", "https://example.com/a", 10, "2026-01-01T00:00:00Z");
        _store.Add("b.zip", @"C:\x\b.zip", "https://example.com/b", 20, "2026-01-02T00:00:00Z");
        var all = _store.All();
        Assert.Equal(2, all.Count);
        // 倒序：最新在前
        Assert.Equal("b.zip", all[0].FileName);
        Assert.Equal(20, all[0].SizeBytes);
        Assert.Equal("a.zip", all[1].FileName);
    }

    [Fact]
    public void Add_NullFields_StoredAsEmpty()
    {
        _store.Add(null!, null!, null!, 0, null!);
        var record = Assert.Single(_store.All());
        Assert.Equal(string.Empty, record.FileName);
        Assert.Equal(string.Empty, record.FilePath);
        Assert.Equal(string.Empty, record.Url);
        Assert.Equal(string.Empty, record.CompletedAt);
    }

    [Fact]
    public void All_RespectsLimit()
    {
        for (var i = 0; i < 5; i++)
            _store.Add($"f{i}.bin", $"C:\\f{i}.bin", $"https://example.com/{i}", i, "t");
        var top2 = _store.All(limit: 2);
        Assert.Equal(2, top2.Count);
        // limit 截断也保持倒序（最新的两条）
        Assert.Equal("f4.bin", top2[0].FileName);
        Assert.Equal("f3.bin", top2[1].FileName);
    }

    [Fact]
    public void Add_PrunesOldestBeyond500()
    {
        // 505 条：超出有界保留上限后最旧的 5 条被修剪
        for (var i = 0; i < 505; i++)
            _store.Add($"f{i}.bin", $"C:\\f{i}.bin", $"https://example.com/{i}", i, "t");
        var all = _store.All(limit: 1000);
        Assert.Equal(500, all.Count);
        Assert.Equal("f504.bin", all[0].FileName);
        Assert.Equal("f5.bin", all[^1].FileName);
    }

    [Fact]
    public void Clear_RemovesAllRecords()
    {
        _store.Add("a.zip", @"C:\a.zip", "https://example.com/a", 1, "t");
        _store.Clear();
        Assert.Empty(_store.All());
    }

    public void Dispose()
    {
        if (File.Exists(_dbPath))
            File.Delete(_dbPath);
    }
}

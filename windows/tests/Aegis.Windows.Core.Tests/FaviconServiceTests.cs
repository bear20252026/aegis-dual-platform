namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Favicons;
using Xunit;

/// <summary>C9 批（审计 2026-09-26）：favicon 磁盘缓存路径形态直测（CS-120）。
/// 仅路径计算无 IO——AppPaths 指向真实用户目录也不落盘。</summary>
public sealed class FaviconServiceTests
{
    [Fact]
    public void CachePathNormalizesHostCase()
    {
        // host 大小写归一——同站点命中同一磁盘文件
        Assert.Equal(
            FaviconService.CachePath("Example.COM"),
            FaviconService.CachePath("example.com"));
    }

    [Fact]
    public void CachePathIsSha1HexPngName()
    {
        // 40 位大写十六进制哈希 + .png 后缀——host 不直接进文件名（路径注入面）
        var path = FaviconService.CachePath("example.com");
        Assert.EndsWith(".png", path);
        var name = Path.GetFileNameWithoutExtension(path);
        Assert.Equal(40, name.Length);
        Assert.Matches("^[0-9A-F]{40}$", name);
    }
}

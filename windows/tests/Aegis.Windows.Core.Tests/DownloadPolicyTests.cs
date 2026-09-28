namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Downloads;
using Xunit;

/// <summary>M3（ADR-009）：下载策略单测——对齐 Android DownloadPolicy
/// （批次 1 修复后语义：尾点/查询串直链/路径段穿越均命中）。</summary>
public sealed class DownloadPolicyTests
{
    [Theory]
    [InlineData("https://x.example/setup.exe", "setup.exe", true)]
    [InlineData("https://x.example/doc.pdf", "doc.pdf", false)]
    [InlineData("https://x.example/download", "x.exe.", true)]
    [InlineData("https://x.example/download?file=x.exe", "", true)]
    [InlineData("https://x.example/p/a/evil.msi", "evil.msi", true)]
    [InlineData("https://x.example/script.ps1", "script.ps1", true)]
    [InlineData("https://x.example/bundle.tar.exe", "bundle.tar.exe", true)]   // CS-108：多级扩展取末段
    [InlineData("https://x.example/archive.tar", "archive.tar", false)]        // tar 本身不危险
    [InlineData("https://x.example/download?f=x%2Fy.exe", "", true)]           // CS-109：编码路径段解到参数值
    public void DangerousExtensionMatrix(string url, string fileName, bool expected)
    {
        Assert.Equal(expected, DownloadPolicy.RequiresExplicitConfirmation(url, fileName));
    }

    [Fact]
    public void EmptyUrlAndFileNameNotDangerous()
    {
        // CS-107：空 url+空文件名不命中（解析失败候选均为空串→无扩展）
        Assert.False(DownloadPolicy.RequiresExplicitConfirmation("", ""));
        Assert.False(DownloadPolicy.RequiresExplicitConfirmation("not a url", ""));
    }

    [Fact]
    public void SanitizeStripsPathTraversal()
    {
        Assert.Equal("evil.exe", DownloadPolicy.SanitizeFileName("../../evil.exe"));
    }

    [Fact]
    public void SanitizeStripsWindowsPath()
    {
        var winPath = "C:" + Path.DirectorySeparatorChar + "Windows" +
                      Path.DirectorySeparatorChar + "evil.exe";
        Assert.Equal("evil.exe", DownloadPolicy.SanitizeFileName(winPath));
    }

    [Fact]
    public void SanitizeKeepsNormalName()
    {
        Assert.Equal("ok_name.pdf", DownloadPolicy.SanitizeFileName("ok_name.pdf"));
    }

    [Fact]
    public void SanitizeStripsTrailingDot()
    {
        Assert.Equal("x.exe", DownloadPolicy.SanitizeFileName("x.exe."));
    }

    [Fact]
    public void SanitizeFallsBackToDefaultName()
    {
        Assert.Equal("aegis_download", DownloadPolicy.SanitizeFileName(""));
    }

    [Fact]
    public void SanitizeTruncationKeepsExtension()
    {
        // CS-252：超长截断保留扩展名——危险扩展不因截断而漏判
        var longName = new string('a', 250) + ".exe";
        var sanitized = DownloadPolicy.SanitizeFileName(longName);
        Assert.True(sanitized.Length <= 201, $"截断后长度 {sanitized.Length}");
        Assert.EndsWith(".exe", sanitized);
        Assert.True(DownloadPolicy.RequiresExplicitConfirmation("https://x.example/d", sanitized));
    }

    [Fact]
    public void SanitizeRemovesControlChars()
    {
        Assert.Equal("badname.zip", DownloadPolicy.SanitizeFileName("bad\x01name.zip"));
    }

    // ===== C19b 批（审计 2026-09-26）：CS-303 截断代理对安全 =====

    [Fact]
    public void SanitizeTruncation_DoesNotSplitSurrogatePair()
    {
        // CS-303：emoji 文件名超长截断——硬切可产生孤立代理（CS-101/155/163/
        // 212 已修同类四处此处漏）。无扩展纯 emoji 段直测：截断产物不以
        // 高代理结尾（下一字符若是低代理即被劈开）
        var noExt = string.Concat(Enumerable.Repeat("\U0001F600", 150));  // 300 个 UTF-16 单元
        var sanitized = DownloadPolicy.SanitizeFileName(noExt);
        Assert.True(sanitized.Length <= 200, $"截断后长度 {sanitized.Length}");
        Assert.False(char.IsHighSurrogate(sanitized[^1]));
        Assert.Equal(0, sanitized.Length % 2);  // 全部为完整代理对
    }

    [Fact]
    public void TruncateSurrogateSafe_CutOnHighSurrogate_BacksOffOne()
    {
        // CS-303 提纯直测：cut 恰落在高代理项上回退一位
        var text = new string('a', 10) + "\U0001F600bc";
        Assert.Equal(new string('a', 10), DownloadPolicy.TruncateSurrogateSafe(text, 11));
        // cut 落在低代理上不回退（对完整保留）
        Assert.Equal(new string('a', 10) + "\U0001F600", DownloadPolicy.TruncateSurrogateSafe(text, 12));
        // 未超长原样返回
        Assert.Equal(text, DownloadPolicy.TruncateSurrogateSafe(text, 50));
    }
}

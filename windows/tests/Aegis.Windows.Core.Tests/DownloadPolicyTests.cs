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
    public void DangerousExtensionMatrix(string url, string fileName, bool expected)
    {
        Assert.Equal(expected, DownloadPolicy.RequiresExplicitConfirmation(url, fileName));
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
    public void SanitizeRemovesControlChars()
    {
        Assert.Equal("badname.zip", DownloadPolicy.SanitizeFileName("bad\x01name.zip"));
    }
}

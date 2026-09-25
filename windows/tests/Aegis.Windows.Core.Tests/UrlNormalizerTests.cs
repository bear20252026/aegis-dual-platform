namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Chrome;
using Xunit;

/// <summary>C11 批（审计 2026-09-26）：地址栏归一补测——未知引擎回退、尾点
/// 判搜索词、about:blank 大小写、host:port 带路径、裸 IPv6 字面量（CS-140）。</summary>
public sealed class UrlNormalizerTests
{
    // ===== CS-138：未知引擎回退默认引擎 =====

    [Theory]
    [InlineData("hello world")]
    [InlineData("天气 查询")]
    public void UnknownEngineKeyFallsBackToDefaultEngine(string query)
    {
        var normalized = UrlNormalizer.Normalize(query, "not-a-real-engine");

        Assert.NotNull(normalized);
        Assert.StartsWith(UrlNormalizer.EngineUrls[UrlNormalizer.DefaultEngine], normalized);
    }

    [Fact]
    public void KnownEngineKeyUsesThatEngine()
    {
        Assert.StartsWith("https://duckduckgo.com/?q=",
            UrlNormalizer.Normalize("hello world", "duckduckgo"));
    }

    // ===== CS-139：尾点输入判搜索词（不补 scheme 导航） =====

    [Theory]
    [InlineData("example.")]
    [InlineData("example.com..")]
    public void TrailingDotInputTreatedAsSearchQuery(string query)
    {
        var normalized = UrlNormalizer.Normalize(query);

        Assert.StartsWith(UrlNormalizer.EngineUrls[UrlNormalizer.DefaultEngine], normalized);
    }

    // ===== CS-141：about:blank 大小写不敏感 =====

    [Theory]
    [InlineData("ABOUT:BLANK")]
    [InlineData("About:Blank")]
    [InlineData("about:blank")]
    public void AboutBlankIsCaseInsensitive(string input) =>
        Assert.Equal("about:blank", UrlNormalizer.Normalize(input));

    // ===== CS-142：host:port 带路径导航 =====

    [Theory]
    [InlineData("localhost:8080/x", "http://localhost:8080/x")]
    [InlineData("127.0.0.1:8080/x", "http://127.0.0.1:8080/x")]
    [InlineData("example.com:8080/x", "https://example.com:8080/x")]
    public void HostPortWithPathNavigates(string input, string expected) =>
        Assert.Equal(expected, UrlNormalizer.Normalize(input));

    // ===== CS-140：裸 IPv6 字面量补 http（此前被当搜索词） =====

    [Theory]
    [InlineData("::1", "http://[::1]")]
    [InlineData("[::1]", "http://[::1]")]
    [InlineData("[::1]:8080", "http://[::1]:8080")]
    [InlineData("[::1]/x", "http://[::1]/x")]
    [InlineData("::1/x", "http://[::1]/x")]
    public void BareIpv6LiteralNavigates(string input, string expected) =>
        Assert.Equal(expected, UrlNormalizer.Normalize(input));

    [Fact]
    public void LetterLeadingColonedInputStaysFailClosed()
    {
        // 字母起始形如 scheme（"fe80:"）——维持 fail-closed 拒绝，不抢道为 IPv6
        Assert.Null(UrlNormalizer.Normalize("fe80::1"));
        // 冒号起始但非合法 IPv6——回退搜索词（与既有行为一致）
        var normalized = UrlNormalizer.Normalize(":::");
        Assert.StartsWith(UrlNormalizer.EngineUrls[UrlNormalizer.DefaultEngine], normalized!);
    }
}

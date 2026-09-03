namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>M1-T2（ADR-009）：威胁黑名单语义单测——Python threat_feed.py 移植
/// 的解析/匹配行为锁。</summary>
public sealed class ThreatFeedTests
{
    [Theory]
    [InlineData("example.com", "example.com")]
    [InlineData("||ads.example.com^", "ads.example.com")]
    [InlineData("! comment", null)]
    [InlineData("# comment", null)]
    [InlineData("", null)]
    [InlineData("https://evil.example/path", "evil.example")]
    [InlineData("notadomain", null)]
    [InlineData("localhost", "localhost")]
    public void ParseFeedLineMatchesPythonSemantics(string line, string? expected)
    {
        Assert.Equal(expected, ThreatFeedUpdater.ParseFeedLine(line));
    }

    [Fact]
    public void BlockedHostsMatchesExactAndSubdomains()
    {
        var blocked = new BlockedHosts(["example.com", "localhost"]);
        Assert.True(blocked.IsBlocked("example.com"));
        Assert.True(blocked.IsBlocked("evil.example.com"));
        Assert.True(blocked.IsBlocked("deep.evil.example.com"));
        Assert.True(blocked.IsBlocked("localhost"));
        // 反向不成立：黑名单里的子域不匹配父域
        Assert.False(blocked.IsBlocked("com"));
    }

    [Fact]
    public void BlockedHostsNormalizesCaseAndTrailingDot()
    {
        var blocked = new BlockedHosts(["EXAMPLE.com."]);
        Assert.True(blocked.IsBlocked("example.COM."));
        Assert.True(blocked.IsBlocked("sub.example.com"));
    }

    [Fact]
    public void EmptyOrWhitespaceHostNeverBlocked()
    {
        var blocked = new BlockedHosts(["example.com"]);
        Assert.False(blocked.IsBlocked(""));
        Assert.False(blocked.IsBlocked("   "));
    }

    [Fact]
    public void ValidateFeedUrlRequiresHttps()
    {
        Assert.NotNull(ThreatFeedUpdater.ValidateFeedUrl("https://feeds.example/list.txt"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("http://feeds.example/list.txt"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("ftp://x"));
        // 离线测试开关：显式开启时 file:// 放行（对齐 Python AEGIS_THREAT_FEED_ALLOW_FILE）
        Assert.NotNull(ThreatFeedUpdater.ValidateFeedUrl("file:///feeds/list.txt", allowFileForOfflineTest: true));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("file:///feeds/list.txt"));
    }

    [Fact]
    public void LoadCachedMissingFileReturnsEmpty()
    {
        var missing = Path.Combine(Path.GetTempPath(), $"no_such_{Guid.NewGuid():N}.txt");
        Assert.Empty(ThreatFeedUpdater.LoadCached(missing));
    }
}

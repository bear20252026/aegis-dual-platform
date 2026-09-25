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

    // ===== CS-057/058（审计 2026-09-25）：边界条目零覆盖补齐 =====

    [Theory]
    [InlineData("||localhost^", "localhost")]           // localhost 白名单（无点仍放行）
    [InlineData("||evil.example:8080^", "evil.example")] // 端口剥离——裸域入表可命中
    [InlineData("||[::1]^", null)]                       // IPv6 字面量含冒号+非法字符 → 拒绝
    [InlineData("https://tracker.example/payload", "tracker.example")]  // 协议+路径残留
    public void ParseFeedLine_BoundaryEntries(string line, string? expected)
    {
        // 此前带端口条目原样入表永不命中（黑名单静默失效面）
        Assert.Equal(expected, ThreatFeedUpdater.ParseFeedLine(line));
    }

    [Theory]
    [InlineData("  https://feeds.example/list.txt  ")]  // 首尾空白裁剪后放行
    [InlineData("\thttps://feeds.example/list.txt\n")]
    public void ValidateFeedUrl_TrimsSurroundingWhitespace(string feedUrl)
    {
        // 此前未 Trim 时带空白的 https 地址被拒（订阅源配置带尾随空格即失效）
        Assert.NotNull(ThreatFeedUpdater.ValidateFeedUrl(feedUrl));
        Assert.Equal("https://feeds.example/list.txt", ThreatFeedUpdater.ValidateFeedUrl(feedUrl));
    }

    // ===== CS-074（审计 2026-09-25）：仅点号 host 不误拦 =====

    [Theory]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData("...")]
    [InlineData(" . ")]
    public void BlockedHosts_DotOnlyHostsNeverBlocked(string host)
    {
        // 归一化（TrimEnd '.'）后为空的 host 一律放行——畸形仅点号 host 不得
        // 触发任何清单命中（防止空串键污染匹配）
        var blocked = new BlockedHosts(["example.com", "localhost"]);
        Assert.False(blocked.IsBlocked(host));
    }

    [Fact]
    public void BlockedHosts_DotOnlyEntry_IsIgnoredAtConstruction()
    {
        // 清单侧仅点号条目在构造期被丢弃——不产生空串键（空串 Contains 会
        // 使任意空 host 命中，语义污染）
        var blocked = new BlockedHosts(new[] { ".", "..", "example.com" });
        Assert.True(blocked.IsBlocked("example.com"));
        Assert.False(blocked.IsBlocked(""));
    }
}

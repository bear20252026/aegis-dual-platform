namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>M1-T2（ADR-009）+ C10 批（审计 2026-09-26 CS-133 合并）：威胁黑名单
/// 语义单测——Python threat_feed.py 移植的解析/匹配行为锁。原 ThreatFeedTests
/// 与 ThreatFeedLogicTests 两文件重复覆盖，合并为单一行为锁文件。</summary>
public sealed class ThreatFeedTests
{
    // ============ ParseFeedLine（合并自两文件矩阵） ============

    [Theory]
    [InlineData("example.com", "example.com")]              // 裸域
    [InlineData("||ads.example.com^", "ads.example.com")]   // AdBlock 主机语法
    [InlineData("||localhost^", "localhost")]               // localhost 白名单（无点仍放行）
    [InlineData("||evil.example:8080^", "evil.example")]    // 端口剥离——裸域入表可命中
    [InlineData("||[::1]^", null)]                          // IPv6 字面量含冒号+非法字符 → 拒绝
    [InlineData("https://evil.example/path", "evil.example")]  // 协议+路径残留
    [InlineData("Tracker.IO:8080", "tracker.io")]           // 端口剥离（否则永不命中）
    [InlineData("  spaced.example  ", "spaced.example")]
    [InlineData("! comment", null)]
    [InlineData("# comment", null)]
    [InlineData("", null)]
    [InlineData("   ", null)]
    [InlineData("*wildcard.example", null)]     // 通配残留拒绝
    [InlineData("under_score.example", null)]   // 非主机字符拒绝
    [InlineData("no-dot-hostname", null)]       // 无点非 localhost 拒绝
    [InlineData("notadomain", null)]
    public void ParseFeedLineMatchesPythonSemantics(string line, string? expected)
    {
        Assert.Equal(expected, ThreatFeedUpdater.ParseFeedLine(line));
    }

    // ============ ValidateFeedUrl（合并自两文件矩阵） ============

    [Fact]
    public void ValidateFeedUrlRequiresHttps()
    {
        Assert.NotNull(ThreatFeedUpdater.ValidateFeedUrl("https://feeds.example/list.txt"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("http://feeds.example/list.txt"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("ftp://x"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("not a url"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl(null));
        // 离线测试开关：显式开启时 file:// 放行（对齐 Python AEGIS_THREAT_FEED_ALLOW_FILE）
        Assert.NotNull(ThreatFeedUpdater.ValidateFeedUrl("file:///feeds/list.txt", allowFileForOfflineTest: true));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("file:///feeds/list.txt"));
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

    // ============ BlockedHosts（合并自两文件矩阵） ============

    [Fact]
    public void BlockedHostsMatchesExactAndSubdomains()
    {
        var blocked = new BlockedHosts(["example.com", "localhost"]);
        Assert.True(blocked.IsBlocked("example.com"));
        Assert.True(blocked.IsBlocked("evil.example.com"));
        Assert.True(blocked.IsBlocked("deep.evil.example.com"));
        Assert.True(blocked.IsBlocked("a.b.c.deep.example.com"));
        Assert.True(blocked.IsBlocked("localhost"));
        // 反向不成立：黑名单里的子域不匹配父域
        Assert.False(blocked.IsBlocked("com"));
        Assert.False(blocked.IsBlocked("bad.example.evil.io"));  // 清单域居前缀不命中
        Assert.False(blocked.IsBlocked("notbad.example"));
    }

    [Fact]
    public void BlockedHostsNormalizesCaseAndTrailingDot()
    {
        var blocked = new BlockedHosts(["EXAMPLE.com."]);
        Assert.True(blocked.IsBlocked("example.COM."));
        Assert.True(blocked.IsBlocked("sub.example.com"));
    }

    [Fact]
    public void BlockedHostsNormalizesWhitespaceEntry()
    {
        var blocked = new BlockedHosts([" Evil.EXAMPLE.com. ", "another.net"]);
        Assert.True(blocked.IsBlocked("evil.example.com"));
        Assert.True(blocked.IsBlocked("EVIL.EXAMPLE.COM"));
        Assert.True(blocked.IsBlocked("sub.evil.example.com"));
        Assert.False(blocked.IsBlocked("example.com"));  // 子域命中不外溢到父域
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData(" . ")]
    public void BlockedHosts_EmptyOrDotOnlyHostsNeverBlocked(string? host)
    {
        // 归一化后为空的 host 一律放行——畸形 host 不得触发任何清单命中
        var blocked = new BlockedHosts(["example.com", "localhost"]);
        Assert.False(blocked.IsBlocked(host!));
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

    [Fact]
    public void NoBlockedHosts_AlwaysAllows()
    {
        Assert.False(NoBlockedHosts.Instance.IsBlocked("doubleclick.net"));
    }

    // ============ LoadCached ============

    [Fact]
    public void LoadCachedMissingFileReturnsEmpty()
    {
        var missing = Path.Combine(Path.GetTempPath(), $"no_such_{Guid.NewGuid():N}.txt");
        Assert.Empty(ThreatFeedUpdater.LoadCached(missing));
    }

    [Fact]
    public void LoadCached_AppliesParseFeedLineFiltering()
    {
        // CS-131：缓存回放与拉取同口径——被篡改/旧版缓存中的脏条目不再绕过
        // 过滤直接入表（注释/通配/端口/协议形态逐行走 ParseFeedLine）
        var path = Path.Combine(Path.GetTempPath(), $"cached_feed_{Guid.NewGuid():N}.txt");
        File.WriteAllLines(path,
        [
            "clean.example",
            "  ||ads.example^  ",
            "https://proto.example/path",
            "TRacker.IO:8080",
            "! comment",
            "",
            "*wildcard.example",
        ]);
        try
        {
            var hosts = ThreatFeedUpdater.LoadCached(path);
            Assert.Equal(
                new[] { "clean.example", "ads.example", "proto.example", "tracker.io" },
                hosts);
        }
        finally
        {
            File.Delete(path);
        }
    }
}

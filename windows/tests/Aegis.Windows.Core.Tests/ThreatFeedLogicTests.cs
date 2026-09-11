namespace Aegis.Windows.Core.Tests;

using System;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>威胁黑名单语义单测（测试缺口批次 3）：BlockedHosts 归一化/精确/
/// 子域后缀匹配；ThreatFeedUpdater 订阅源校验（https 强制、file 离线开关）
/// 与 AdBlock 行语法解析（||host^ / 注释 / 端口剥离 / 字符白名单）。</summary>
public class ThreatFeedLogicTests
{
    // ============ BlockedHosts ============

    [Fact]
    public void BlockedHosts_NormalizesInput()
    {
        var hosts = new BlockedHosts(new[] { " Evil.EXAMPLE.com. ", "another.net" });
        Assert.True(hosts.IsBlocked("evil.example.com"));
        Assert.True(hosts.IsBlocked("EVIL.EXAMPLE.COM"));
        Assert.True(hosts.IsBlocked("sub.evil.example.com"));
        Assert.False(hosts.IsBlocked("example.com"));  // 只命中黑名单元件本身及以上子域
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData(".")]
    public void BlockedHosts_EmptyHost_NeverBlocked(string? host)
    {
        var hosts = new BlockedHosts(new[] { "blocked.example" });
        Assert.False(hosts.IsBlocked(host!));
    }

    [Fact]
    public void BlockedHosts_DeepSubdomain_MatchesAncestorSuffix()
    {
        var hosts = new BlockedHosts(new[] { "bad.io" });
        Assert.True(hosts.IsBlocked("a.b.c.bad.io"));
        Assert.False(hosts.IsBlocked("bad.io.evil.com"));  // 清单域出现在前缀不命中
        Assert.False(hosts.IsBlocked("notbad.io"));
    }

    [Fact]
    public void NoBlockedHosts_AlwaysAllows()
    {
        Assert.False(NoBlockedHosts.Instance.IsBlocked("doubleclick.net"));
    }

    // ============ ThreatFeedUpdater.ValidateFeedUrl ============

    [Fact]
    public void ValidateFeedUrl_OnlyHttps_OrFileWithOfflineFlag()
    {
        Assert.Equal("https://feeds.example/list.txt",
            ThreatFeedUpdater.ValidateFeedUrl("https://feeds.example/list.txt"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("http://feeds.example/list.txt"));  // 明文拒
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("ftp://feeds.example/list.txt"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("not a url"));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl(null));
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("  "));
        // file:// 仅显式离线测试开关
        Assert.Null(ThreatFeedUpdater.ValidateFeedUrl("file:///C:/feed.txt"));
        Assert.Equal("file:///C:/feed.txt",
            ThreatFeedUpdater.ValidateFeedUrl("file:///C:/feed.txt", allowFileForOfflineTest: true));
    }

    // ============ ThreatFeedUpdater.ParseFeedLine ============

    [Theory]
    [InlineData("||doubleclick.net^", "doubleclick.net")]   // AdBlock 主机语法
    [InlineData("doubleclick.net", "doubleclick.net")]       // 裸域
    [InlineData("https://tracker.io/path", "tracker.io")]    // 带协议与路径残留
    [InlineData("Tracker.IO:8080", "tracker.io")]            // 端口剥离（否则永不命中）
    [InlineData("localhost", "localhost")]                   // 无点单机名豁免
    [InlineData("  spaced.example  ", "spaced.example")]
    public void ParseFeedLine_ValidEntries(string line, string expected)
    {
        Assert.Equal(expected, ThreatFeedUpdater.ParseFeedLine(line));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("! adblock comment")]
    [InlineData("# hash comment")]
    [InlineData("*wildcard.example")]     // 通配残留拒绝
    [InlineData("under_score.example")]   // 非主机字符拒绝
    [InlineData("no-dot-hostname")]       // 无点非 localhost 拒绝
    public void ParseFeedLine_InvalidEntries_ReturnNull(string line)
    {
        Assert.Null(ThreatFeedUpdater.ParseFeedLine(line));
    }
}

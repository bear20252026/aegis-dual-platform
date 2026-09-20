namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>威胁黑名单刷新编排单测（上帝对象拆分·第六批）：启动即应用缓存
/// 快照；订阅源缺失/非法不启动刷新；合法源后台刷新替换快照；刷新失败保持
/// 旧快照。全部副作用注入——离线可测。</summary>
public sealed class ThreatFeedCoordinatorTests
{
    private readonly string _cachePath =
        Path.Combine(Path.GetTempPath(), $"aegis_threat_{Guid.NewGuid():N}.txt");

    private readonly List<string> _logs = new();

    private sealed class Harness
    {
        public readonly List<IBlockedHosts> Applied = new();
        public readonly List<string> Logs = new();
        public string? FeedUrl = "https://feeds.example/list.txt";
        public string[] FetchedCacheContents = Array.Empty<string>();

        public ThreatFeedCoordinator Build(string cachePath) =>
            new(
                applyHosts: applied => Applied.Add(applied),
                cachePath,
                () => FeedUrl,
                message => Logs.Add(message),
                (url, cache) =>
                {
                    Assert.StartsWith("https://", url);
                    File.WriteAllLines(cache, FetchedCacheContents);
                    return FetchedCacheContents;
                });
    }

    public ThreatFeedCoordinatorTests()
    {
        File.WriteAllLines(_cachePath, ["doubleclick.net", "tracker.example"]);
    }

    [Fact]
    public void Start_AppliesCachedSnapshot_Immediately()
    {
        var h = new Harness();
        var c = h.Build(_cachePath);
        c.Start();
        var applied = Assert.Single(h.Applied);
        Assert.True(applied.IsBlocked("doubleclick.net"));
        Assert.True(applied.IsBlocked("sub.tracker.example"));
        Assert.False(applied.IsBlocked("example.com"));
        Assert.Contains("[threat] 黑名单快照 2 条", h.Logs);
    }

    [Fact]
    public void Start_WithoutFeedUrl_AppliesSnapshotOnly_NoRefresh()
    {
        var h = new Harness { FeedUrl = null };
        var c = h.Build(_cachePath);
        var started = c.Start();
        Assert.False(started);
        Assert.Single(h.Applied); // 仅快照，无刷新替换
    }

    [Fact]
    public void Start_InvalidFeedUrl_LogsAndKeepsSnapshot()
    {
        var h = new Harness { FeedUrl = "http://plain.example/list.txt" }; // 明文拒
        var c = h.Build(_cachePath);
        var started = c.Start();
        Assert.False(started);
        Assert.Contains(h.Logs, l => l.Contains("订阅源非法"));
        Assert.Single(h.Applied);
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_ValidFeed_RefreshesAndReplacesSnapshot()
    {
        var h = new Harness { FetchedCacheContents = ["refreshed.example"] };
        var c = h.Build(_cachePath);
        Assert.True(c.Start());
        // 等待后台刷新完成
        await SpinUntil(() => h.Applied.Count >= 2);
        var final = h.Applied[^1];
        Assert.True(final.IsBlocked("refreshed.example"));
        Assert.False(final.IsBlocked("doubleclick.net")); // 旧快照被替换
        Assert.Contains(h.Logs, l => l.Contains("订阅源刷新完成"));
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_RefreshFailure_KeepsOldSnapshot()
    {
        var h = new Harness();
        var c = new ThreatFeedCoordinator(
            applyHosts: applied => h.Applied.Add(applied),
            _cachePath,
            () => h.FeedUrl,
            message => h.Logs.Add(message),
            fetchAndStore: (_, _) => throw new InvalidOperationException("网络不可用"));
        Assert.True(c.Start());
        await SpinUntil(() => h.Logs.Any(l => l.Contains("订阅源刷新失败")));
        // 快照从未被替换（仍只有初始一次）
        Assert.Single(h.Applied);
    }

    private static async System.Threading.Tasks.Task SpinUntil(Func<bool> condition, int timeoutMs = 3000)
    {
        var deadline = Environment.TickCount64 + timeoutMs;
        while (!condition())
        {
            if (Environment.TickCount64 > deadline)
                throw new TimeoutException("后台任务未在时限内完成");
            await System.Threading.Tasks.Task.Delay(10);
        }
    }

    public void Dispose()
    {
        if (File.Exists(_cachePath))
            File.Delete(_cachePath);
    }
}
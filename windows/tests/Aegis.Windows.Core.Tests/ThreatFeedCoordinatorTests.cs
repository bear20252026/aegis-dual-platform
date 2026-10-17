namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Aegis.Windows.Core.Security;
using Aegis.Windows.TestSupport;
using Xunit;

/// <summary>威胁黑名单刷新编排单测（上帝对象拆分·第六批）：启动后台应用缓存
/// 快照（CS-350：LoadCached 移出 UI 线程——空快照启动+后台加载）；订阅源
/// 缺失/非法不启动刷新；合法源后台刷新替换快照；刷新失败保持旧快照。
/// 全部副作用注入——离线可测。
///
/// 本类只覆盖**启动那一次**的链路，所以一律传 `refreshInterval: TimeSpan.Zero`
/// 关掉 Q52 的周期重取：留着默认节拍，BackgroundTask 永不完成，下面的
/// `await BackgroundTask`（= 等后台链收工，防 Dispose 与写盘抢句柄）会直接挂死。
/// 周期/退避/立即刷这些新行为在 ThreatFeedRefreshScheduleTests 覆盖。</summary>
public sealed class ThreatFeedCoordinatorTests : IDisposable
{
    private readonly string _cachePath =
        Path.Combine(Path.GetTempPath(), $"aegis_threat_{Guid.NewGuid():N}.txt");

    private readonly List<string> _logs = new();

    private sealed class Harness
    {
        // 记录面走 ThreadSafeRecorder：写侧是协调器的后台线程，读侧是本文件里每 10ms
        // 一轮的 SpinUntil 枚举——普通 List 在这个读法下抛 Collection was modified
        // （台账 §五 Q62 = R9-CS-19，CI 实测红在 :65 那一轮）。
        public readonly ThreadSafeRecorder<IBlockedHosts> Applied = new();
        public readonly ThreadSafeRecorder<string> Logs = new();
        public string? FeedUrl = "https://feeds.example/list.txt";
        public string[] FetchedCacheContents = Array.Empty<string>();

        public ThreatFeedCoordinator Build(string cachePath) =>
            new(
                applyHosts: applied => Applied.Record(applied),
                cachePath,
                () => FeedUrl,
                message => Logs.Record(message),
                (url, cache) =>
                {
                    Assert.StartsWith("https://", url);
                    File.WriteAllLines(cache, FetchedCacheContents);
                    return FetchedCacheContents;
                },
                refreshInterval: TimeSpan.Zero);   // 见类注释：本类只测启动那一次
    }

    public ThreatFeedCoordinatorTests()
    {
        File.WriteAllLines(_cachePath, ["doubleclick.net", "tracker.example"]);
    }

    private IBlockedHosts LastApplied(Harness h) => h.Applied[^1];

    [Fact]
    public async System.Threading.Tasks.Task Start_AppliesCachedSnapshot_InBackground()
    {
        // CS-350：快照加载移到后台任务（此前 Start 内同步 LoadCached——
        // 启动链 UI 线程 ≤5MB 读盘）；等待后台应用完成后语义不变。
        // 取"含缓存快照内容的这一次应用"断言——后台刷新可能随后替换 Applied，
        // 不能按 last 元素断言（竞态）
        var h = new Harness();
        var c = h.Build(_cachePath);
        c.Start();
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        await SpinUntil(() => h.Logs.Any(l => l.Contains("黑名单快照 2 条")));
        var applied = h.Applied.First(b => b is BlockedHosts blk && blk.IsBlocked("doubleclick.net"));
        Assert.True(applied.IsBlocked("sub.tracker.example"));
        Assert.False(applied.IsBlocked("example.com"));
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_WithoutFeedUrl_AppliesSnapshotOnly_NoRefresh()
    {
        var h = new Harness { FeedUrl = null };
        var c = h.Build(_cachePath);
        var started = c.Start();
        Assert.False(started);
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any());
        Assert.Single(h.Applied); // 仅快照，无刷新替换
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_InvalidFeedUrl_LogsAndKeepsSnapshot()
    {
        var h = new Harness { FeedUrl = "http://plain.example/list.txt" }; // 明文拒
        var c = h.Build(_cachePath);
        var started = c.Start();
        Assert.False(started);
        Assert.Contains(h.Logs, l => l.Contains("订阅源非法"));
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any());
        Assert.Single(h.Applied);
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_ValidFeed_RefreshesAndReplacesSnapshot()
    {
        var h = new Harness { FetchedCacheContents = ["refreshed.example"] };
        var c = h.Build(_cachePath);
        Assert.True(c.Start());
        // 等待后台刷新完成（快照应用 + 刷新替换共两次）
        await SpinUntil(() => h.Applied.Count >= 2);
        var final = LastApplied(h);
        Assert.True(final.IsBlocked("refreshed.example"));
        Assert.False(final.IsBlocked("doubleclick.net")); // 旧快照被替换
        Assert.Contains(h.Logs, l => l.Contains("订阅源刷新完成"));
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_RefreshFailure_KeepsOldSnapshot()
    {
        var h = new Harness();
        var c = new ThreatFeedCoordinator(
            applyHosts: applied => h.Applied.Record(applied),
            _cachePath,
            () => h.FeedUrl,
            message => h.Logs.Record(message),
            fetchAndStore: (_, _) => throw new InvalidOperationException("网络不可用"),
            refreshInterval: TimeSpan.Zero);
        Assert.True(c.Start());
        await SpinUntil(() => h.Logs.Any(l => l.Contains("订阅源刷新失败")));
        // 快照未被替换（仍只有后台应用的一次），且内容保持缓存快照
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any());
        Assert.Single(h.Applied);
        Assert.True(LastApplied(h).IsBlocked("doubleclick.net"));
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task Start_WhitespaceFeedUrl_TreatedAsMissing()
    {
        // CS-245：空白订阅源地址裁剪后视为未配置——不启动刷新
        var h = new Harness { FeedUrl = "   " };
        var c = h.Build(_cachePath);
        Assert.False(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any());
        Assert.Single(h.Applied);
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task BackgroundTask_CoversBothSnapshotApplyAndRefresh()
    {
        // R8-CS-CORE-12：句柄必须罩住整条后台链（快照应用 → 刷新），只交回前半段
        // 等于没修——Dispose 仍会与刷新写盘抢句柄。断言在 await 之后：Applied 两次、
        // 刷新日志已落，缺一不可。
        var h = new Harness { FetchedCacheContents = ["refreshed.example"] };
        var c = h.Build(_cachePath);
        c.Start();
        Assert.NotNull(c.BackgroundTask);
        await c.BackgroundTask!;
        Assert.Equal(2, h.Applied.Count);
        Assert.Contains(h.Logs, l => l.Contains("订阅源刷新完成"));
    }

    [Fact]
    public async System.Threading.Tasks.Task Refresh_AppliesFetchedList_Directly()
    {
        // CS-134：刷新后直接用 fetchAndStore 返回值——此前写盘后再重读磁盘，
        // 缓存文件若此刻被第三方改写会应用非拉取内容（且多一次全量 IO）
        var h = new Harness();
        var c = new ThreatFeedCoordinator(
            applyHosts: applied => h.Applied.Record(applied),
            _cachePath,
            () => h.FeedUrl,
            message => h.Logs.Record(message),
            fetchAndStore: (_, cache) =>
            {
                File.WriteAllLines(cache, new[] { "stale-from-disk.example" });
                return new[] { "fresh-from-fetch.example" };
            },
            refreshInterval: TimeSpan.Zero);
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.Count >= 2);
        var final = LastApplied(h);
        Assert.True(final.IsBlocked("fresh-from-fetch.example"));
        Assert.False(final.IsBlocked("stale-from-disk.example"));
            await SettleAsync(c);  // 等后台链收工，别与 Dispose 抢缓存文件
    }

    [Fact]
    public async System.Threading.Tasks.Task Clear_releases_the_list_and_deletes_the_cache()
    {
        // R9-B86（Q54 用户定「清空即解除」）：清空要同时做掉两件事——内存里那份名单解除、
        // 缓存文件删掉（不然下次启动 `Start()` 又无条件 LoadCached 把它装回来）。
        var deleted = new List<string?>();
        var h = new Harness();
        var c = new ThreatFeedCoordinator(
            applyHosts: applied => h.Applied.Record(applied),
            _cachePath,
            () => h.FeedUrl,
            message => h.Logs.Record(message),
            fetchAndStore: (_, _) => Array.Empty<string>(),
            refreshInterval: TimeSpan.Zero,
            deleteCache: path => deleted.Add(path));
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        Assert.True(await c.ClearAndDisableAsync());
        await SettleAsync(c);
        Assert.Equal(_cachePath, Assert.Single(deleted));
        Assert.False(LastApplied(h).IsBlocked("doubleclick.net"));
        Assert.False(LastApplied(h).IsBlocked("tracker.example"));
        Assert.Contains(h.Logs, l => l.Contains("黑名单已解除"));
        Assert.Contains(h.Logs, l => l.Contains("缓存文件已删除"));
    }

    [Fact]
    public async System.Threading.Tasks.Task Clear_beats_an_inflight_refresh_on_the_final_state()
    {
        // 这条是本批唯一真正的性质测试：清空必须**排在**在途抓取之后生效。
        // 协调器持着 _refreshGate，所以 ClearAndDisableAsync 会等这次抓取落定再 apply 空名单。
        // 哪天有人去掉那道闸（或把清空改成前插/不等），旧名单会后到并把 doubleclick 装回来——
        // 用户按了「清空」、也看到了那句提示，防护却在线上继续拦（= Q54 反过来发作）。
        var gate = new System.Threading.Tasks.TaskCompletionSource();
        var h = new Harness { FetchedCacheContents = ["late-block.example"] };
        var c = new ThreatFeedCoordinator(
            applyHosts: applied => h.Applied.Record(applied),
            _cachePath,
            () => h.FeedUrl,
            message => h.Logs.Record(message),
            fetchAndStore: (_, cache) =>
            {
                File.WriteAllLines(cache, h.FetchedCacheContents);
                if (!gate.Task.Wait(3000))
                    throw new TimeoutException("在途抓取没等到放行：这条用例的窗口没走通");
                return h.FetchedCacheContents;
            },
            refreshInterval: TimeSpan.Zero,
            deleteCache: _ => { });
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        h.FeedUrl = null;                       // 模拟设置页把订阅源清空（保存后解析不到源）
        var clearing = c.ClearAndDisableAsync();
        gate.SetResult();                       // 让那次「先发出、后完成」的抓取跑完
        Assert.True(await clearing);
        await SettleAsync(c);
        // 非空心判据：快照 + 迟到的刷新 + 清空，三次应用都发生才算踩到那个窗口
        Assert.True(h.Applied.Count >= 3, $"只应用了 {h.Applied.Count} 次：竞态窗口没走到，这条恒绿");
        Assert.False(LastApplied(h).IsBlocked("late-block.example"));
        Assert.False(LastApplied(h).IsBlocked("doubleclick.net"));
    }

    [Fact]
    public async System.Threading.Tasks.Task Clear_with_a_failing_delete_still_releases_the_list()
    {
        // 方向要说清：删除失败**不回退解除**。用户要的「关掉」已经当场生效，
        // 残留一个缓存文件是可诊断的问题——但要留痕，因为它意味着重启会重新加载旧名单。
        var h = new Harness();
        var c = new ThreatFeedCoordinator(
            applyHosts: applied => h.Applied.Record(applied),
            _cachePath,
            () => h.FeedUrl,
            message => h.Logs.Record(message),
            fetchAndStore: (_, _) => Array.Empty<string>(),
            refreshInterval: TimeSpan.Zero,
            deleteCache: _ => throw new IOException("used by another process"));
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        Assert.False(await c.ClearAndDisableAsync());
        await SettleAsync(c);
        Assert.False(LastApplied(h).IsBlocked("doubleclick.net"));
        Assert.Contains(h.Logs, l => l.Contains("黑名单已解除"));
        Assert.Contains(h.Logs, l => l.Contains("重启后仍会从该文件加载"));
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

    /// <summary>等 Start() 投递的那条后台链（快照应用 → 刷新）收工。不等的话，
    /// Dispose 删缓存文件与后台写盘之间没有 happens-before——第八轮实测把必需检查
    /// windows-contract-build 打红（IOException "...being used by another process"）。
    /// 句柄来自 ThreatFeedCoordinator.BackgroundTask：CS-350 把 LoadCached 移出 UI 线程时
    /// 没留下任何可等待的东西，调用方只能轮询副作用。</summary>
    private static async System.Threading.Tasks.Task SettleAsync(ThreatFeedCoordinator coordinator) =>
        await (coordinator.BackgroundTask ?? System.Threading.Tasks.Task.CompletedTask);

    public void Dispose()
    {
        try
        {
            if (File.Exists(_cachePath))
                File.Delete(_cachePath);
        }
        catch (IOException)
        {
            // 后台句柄仍未释放：留一个 GUID 命名的临时文件不影响判定，
            // 也不让清理动作把已经通过的用例反手打红。
        }
    }
}

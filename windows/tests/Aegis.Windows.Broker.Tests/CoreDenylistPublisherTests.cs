namespace Aegis.Windows.Broker.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>审计第六轮遗留缺口收口（2026-10-04）：核心 host 黑名单发布口的行为锁定。
/// 全部走 CoreDenylistPublisher 的注入缝（CS-364 租约工厂缝同型）——不依赖原生
/// DLL，因此这些用例在任何机器上都真实执行、绝不会被静默跳过：缺口藏了五轮的
/// 根因正是"零痕迹"，所以这里的每条推送计数与每条留痕都要断言。
/// CS-346：SecurityLog 重定向临时目录（本类全部留痕断言都读这个文件）。</summary>
public sealed class CoreDenylistPublisherTests : IDisposable
{
    private readonly string _logDir =
        Path.Combine(Path.GetTempPath(), $"aegis_core_denylist_{Guid.NewGuid():N}");

    private readonly List<IReadOnlyCollection<string>> _pushed = new();

    private CoreDenylistOutcome _outcome = CoreDenylistOutcome.Published;
    private int _accepted;
    private string _detail = "ok";

    public CoreDenylistPublisherTests()
    {
        Directory.CreateDirectory(_logDir);
        SecurityLog.SecurityLogDirOverride = _logDir;
        CoreDenylistPublisher.ResetForTests();
        CoreDenylistPublisher.CorePushForTests = hosts =>
        {
            _pushed.Add(hosts);
            return _outcome switch
            {
                CoreDenylistOutcome.Published => CoreDenylistUpdateResult.Apply(hosts.Count, hosts.Count),
                CoreDenylistOutcome.PartiallyPublished => CoreDenylistUpdateResult.Apply(_accepted, hosts.Count),
                CoreDenylistOutcome.ExportMissing => CoreDenylistUpdateResult.MissingExport(hosts.Count),
                _ => CoreDenylistUpdateResult.NotPublished(hosts.Count, _detail),
            };
        };
    }

    private string LogPath => Path.Combine(_logDir, "security.log");

    private string[] LogLines() =>
        File.Exists(LogPath) ? File.ReadAllLines(LogPath) : Array.Empty<string>();

    public void Dispose()
    {
        CoreDenylistPublisher.ResetForTests();
        SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(_logDir, true); } catch (IOException) { }
    }

    // ===== 单一权威源：推出去的就是托管侧在用的那个集合 =====
    // ===== R8-CS-SEC-09（第八轮）：多批推送序列必须单飞 =====

    [Fact]
    public async Task ConcurrentPushes_AreSingleFlight_AndTheQueuedOneCarriesTheLatestSnapshot()
    {
        // UpdateHostDenylist 一次调用=「首批 clear=1 + 其余 clear=0」的**序列**
        //（核心单载荷 64KiB vs 托管 5MiB 订阅源）。两次推送交错 ⇒ 核心最终是
        // 两份快照的混合，且后到的 clear=1 会抹掉对方已追加的条目。
        var inFlight = 0;
        var overlapped = false;
        var firstEntered = new ManualResetEventSlim(false);
        var releaseFirst = new ManualResetEventSlim(false);
        CoreDenylistPublisher.CorePushForTests = hosts =>
        {
            if (Interlocked.Increment(ref inFlight) != 1)
                overlapped = true;
            _pushed.Add(hosts);
            if (hosts.Count == 1)  // 第一份快照在门内等第二份排队，好把交错做实
            {
                firstEntered.Set();
                releaseFirst.Wait(TimeSpan.FromSeconds(10));
            }

            Interlocked.Decrement(ref inFlight);
            return CoreDenylistUpdateResult.Apply(hosts.Count, hosts.Count);
        };

        var first = Task.Run(() => new SharedBlockedHosts().Publish(new BlockedHosts(["a.example"])));
        Assert.True(firstEntered.Wait(TimeSpan.FromSeconds(10)), "第一次推送未进入");

        var second = Task.Run(
            () => new SharedBlockedHosts().Publish(new BlockedHosts(["b.example", "c.example"])));
        SpinWait.SpinUntil(() => Volatile.Read(ref inFlight) >= 0, TimeSpan.FromMilliseconds(200));
        Assert.Single(_pushed);  // 第二份还堵在门外——单飞成立

        releaseFirst.Set();
        await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(10));

        Assert.False(overlapped, "两次推送序列重叠进入了核心");
        Assert.Collection(
            _pushed,
            pushed => Assert.Single(pushed),
            pushed => Assert.Equal(2, pushed.Count));  // 门内重读 ⇒ 排队的推送带的是最新快照
    }


    [Fact]
    public void SnapshotChange_PushesTheManagedSetItself_NotADriftingCopy()
    {
        var blocked = new BlockedHosts(["evil.example", "ads.tracker.example"]);

        new SharedBlockedHosts().Publish(blocked);

        // 断言引用同一性（不是"内容相等"）——两份名单一旦分叉就会重现本缺口
        Assert.Same(blocked.Hosts, Assert.Single(_pushed));
        Assert.Equal(2, _pushed[0].Count);
    }

    [Fact]
    public void EmptySnapshot_PushesEmptyListSoCoreClearsToo()
    {
        // 托管侧回退空名单时核心侧必须同步清空——否则已撤销的条目在核心残留
        new SharedBlockedHosts().Publish(NoBlockedHosts.Instance);

        Assert.Empty(Assert.Single(_pushed));
    }

    [Fact]
    public void UnenumerableSource_DoesNotPush_AndSaysSoLoudly()
    {
        var blocked = new BlockedHosts(["keep.example"]);
        new SharedBlockedHosts().Publish(blocked);
        var prior = CoreDenylistPublisher.CurrentSnapshot;

        new SharedBlockedHosts().Publish(new OpaqueBlockedHosts());

        // 不猜、不复制出一份可能分叉的名单：保留旧快照 + 显式留痕
        Assert.Single(_pushed);
        Assert.Same(prior, CoreDenylistPublisher.CurrentSnapshot);
        Assert.Contains(LogLines(), l => l.Contains("不可枚举"));
    }

    // ===== 可观测性：offered vs accepted，且 accepted < input 必须点名 =====

    [Fact]
    public void AcceptedLessThanInput_IsSurfacedAsDeadBlocklistEntries()
    {
        (_outcome, _accepted) = (CoreDenylistOutcome.PartiallyPublished, 2);

        new SharedBlockedHosts().Publish(new BlockedHosts(["a.example", "b.example", "c.example"]));

        var line = Assert.Single(LogLines(), l => l.Contains("[core-denylist]"));
        Assert.Contains("只接受 2/3", line, StringComparison.Ordinal);
        Assert.Contains("死条目", line, StringComparison.Ordinal);
    }

    [Fact]
    public void FullAccept_LogsOfferedAgainstAccepted()
    {
        new SharedBlockedHosts().Publish(new BlockedHosts(["a.example", "b.example"]));

        Assert.Contains(LogLines(), l => l.Contains("已发布 2/2"));
    }

    [Fact]
    public void MissingExport_LogsDegradationExactlyOnceAcrossEveryRefresh()
    {
        _outcome = CoreDenylistOutcome.ExportMissing;
        var holder = new SharedBlockedHosts();

        holder.Publish(new BlockedHosts(["a.example"]));
        holder.Publish(new BlockedHosts(["a.example", "b.example"]));
        holder.Publish(NoBlockedHosts.Instance);

        Assert.Equal(3, _pushed.Count);  // 每次都照常尝试（降级不是放弃）
        Assert.Single(LogLines(), l => l.Contains("未导出 host 黑名单入口"));
    }

    [Fact]
    public void NotPublished_LogsReasonAndCarriesNoLocalPath()
    {
        _outcome = CoreDenylistOutcome.NotPublished;
        _detail = "native_response_not_utf8";

        new SharedBlockedHosts().Publish(new BlockedHosts(["a.example"]));

        var line = Assert.Single(LogLines(), l => l.Contains("核心黑名单未发布"));
        Assert.Contains("native_response_not_utf8", line, StringComparison.Ordinal);
        // 需求：日志不含任何本机绝对路径
        Assert.DoesNotContain(_logDir, line, StringComparison.Ordinal);
        Assert.DoesNotContain("C:\\", line, StringComparison.Ordinal);
    }

    // ===== 两个推送时机：快照变更 + 桥建立（顺序无关） =====

    [Fact]
    public void BridgeCreatedAfterFirstSnapshot_RepushesCurrentSnapshot()
    {
        // 缺陷形态：broker 在第一次快照加载之后才建桥——不补推则核心整会话空名单
        var blocked = new BlockedHosts(["late.example"]);
        new SharedBlockedHosts().Publish(blocked);
        Assert.Single(_pushed);

        CoreDenylistPublisher.OnSharedBridgeCreated();

        Assert.Equal(2, _pushed.Count);
        Assert.Same(blocked.Hosts, _pushed[1]);
        Assert.Contains(LogLines(), l => l.Contains("原生桥建立"));
    }

    [Fact]
    public void BridgeCreatedBeforeAnySnapshot_IsSilentNoOp()
    {
        CoreDenylistPublisher.OnSharedBridgeCreated();

        Assert.Empty(_pushed);
        Assert.Empty(LogLines());
    }

    [Fact]
    public void NativeCoreNotEngaged_PublishIsNoOpNotAnError()
    {
        // 无桥 = 原生核心没接入（环境变量与安装期标记都没置位的常态）：
        // 必须无操作、不抛、不留错误痕迹
        CoreDenylistPublisher.CorePushForTests = null;
        CoreDenylistPublisher.BridgeProviderForTests = () => null;

        new SharedBlockedHosts().Publish(new BlockedHosts(["a.example", "b.example"]));
        CoreDenylistPublisher.OnSharedBridgeCreated();

        Assert.Empty(LogLines());
        Assert.Equal(2, CoreDenylistPublisher.CurrentSnapshot!.Count);  // 快照仍被记录，待桥出现时补推
    }

    // ===== 生产链：订阅源编排 → broker → 进程级持有者 → 核心 =====

    [Fact]
    public void BrokerUpdateBlockedHosts_RoutesThroughSharedHolderIntoCore()
    {
        var holder = new SharedBlockedHosts();
        using var broker = new BrowserPolicyBroker(
            blockedHosts: holder, nativePolicyCoreRequiredForTests: false);

        broker.UpdateBlockedHosts(new BlockedHosts(["via-broker.example"]));
        Assert.Single(_pushed);

        broker.UpdateBlockedHosts(null);  // CS-017 回退空名单——同样要下推
        Assert.Equal(2, _pushed.Count);
        Assert.Empty(_pushed[1]);
    }

    [Fact]
    public async Task ThreatFeedCoordinator_StartupSnapshotAndRefresh_BothReachCore()
    {
        // 与 MainWindow.StartThreatFeedRefresh 同一条生产链：协调器 apply →
        // broker.UpdateBlockedHosts → SharedBlockedHosts.Publish → 核心发布
        var cache = Path.Combine(_logDir, "threat_feed.txt");
        File.WriteAllLines(cache, ["cached.example"]);
        var holder = new SharedBlockedHosts();
        using var broker = new BrowserPolicyBroker(
            blockedHosts: holder, nativePolicyCoreRequiredForTests: false);
        var coordinator = new ThreatFeedCoordinator(
            applyHosts: hosts => broker.UpdateBlockedHosts(hosts),
            cache,
            () => "https://feeds.example/list.txt",
            _ => { },
            fetchAndStore: (_, path) =>
            {
                File.WriteAllLines(path, ["refreshed.example"]);
                return new[] { "refreshed.example" };
            });

        Assert.True(coordinator.Start());
        await WaitUntil(() => _pushed.Count >= 2);

        // ①启动缓存快照 ②订阅源刷新快照——两次都进核心，且是各自的权威集合
        Assert.Contains("cached.example", _pushed[0]);
        Assert.Contains("refreshed.example", _pushed[^1]);
        Assert.DoesNotContain("cached.example", _pushed[^1]);
    }

    private static async Task WaitUntil(Func<bool> condition, int timeoutMs = 5000)
    {
        var deadline = Environment.TickCount64 + timeoutMs;
        while (!condition())
        {
            if (Environment.TickCount64 > deadline)
                throw new TimeoutException("核心黑名单发布未在时限内完成（不得静默通过）");
            await Task.Delay(10);
        }
    }

    private sealed class OpaqueBlockedHosts : IBlockedHosts
    {
        public bool IsBlocked(string host) => false;
    }
}

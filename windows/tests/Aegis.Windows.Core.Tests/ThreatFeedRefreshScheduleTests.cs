namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>Q52（外部第三轮审计 AEG-008）：威胁订阅源的周期重取与失败退避。
///
/// 修掉的形态：`Start()` 在启动链里取一次就再也不取（旧文案也确实承诺下次启动才生效），
/// 长时间不关窗的用户一直用同一份名单。现在首刷之后按节拍重取、失败按 2 的幂退避
/// （只拉长，绝不缩短——「失败就更快重试」在订阅源 429 时就是自伤）。
///
/// 节拍是唯一不可测面（「真的等 6 小时」），因此 [delay]/[clock]/[cancellation] 全部注入，
/// 注入后等待序列可直接断言。「未配置源 ⇒ 零网络活动」这条既有判据在周期化之后单独钉住；
/// 「清空订阅源后已生效名单仍然拦截」也钉住（放松防护的方向待裁决，见台账 §五）。</summary>
public sealed class ThreatFeedRefreshScheduleTests : IDisposable
{
    private static readonly TimeSpan Six = TimeSpan.FromHours(6);

    private readonly string _cachePath =
        Path.Combine(Path.GetTempPath(), $"aegis_threatloop_{Guid.NewGuid():N}.txt");

    private readonly List<string> _logs = new();

    public ThreatFeedRefreshScheduleTests() =>
        File.WriteAllLines(_cachePath, new[] { "stale.example" });

    public void Dispose()
    {
        try { File.Delete(_cachePath); } catch (IOException) { }
    }

    /// <summary>可注入的假节拍：记下每次请求的时长，并在请求末尾抛取消（与 Task.Delay 同形）。
    /// [cancelAfterTicks] 用来收口「这一轮不碰网络」的循环——那种场景按抓取次数收口永远等不到。</summary>
    private sealed class FakeClock
    {
        public List<TimeSpan> Delays { get; } = new();
        public CancellationTokenSource Cancel { get; } = new();
        public int CancelAfterTicks { get; init; }

        public Task Delay(TimeSpan span, CancellationToken token)
        {
            Delays.Add(span);
            if (CancelAfterTicks > 0 && Delays.Count >= CancelAfterTicks) Cancel.Cancel();
            token.ThrowIfCancellationRequested();
            return Task.CompletedTask;
        }
    }

    private ThreatFeedCoordinator Build(
        Func<string?> resolveUrl,
        Func<string, string, IReadOnlyList<string>> fetch,
        FakeClock clock,
        TimeSpan interval) =>
        new(
            _ => { },
            _cachePath,
            resolveUrl,
            _logs.Add,
            fetch,
            interval,
            clock.Delay,
            () => new DateTimeOffset(2026, 10, 11, 12, 0, 0, TimeSpan.Zero),
            clock.Cancel.Token);

    private static void AssertDelays(FakeClock clock, params double[] hours)
    {
        Assert.Equal(hours.Length, clock.Delays.Count);
        for (var i = 0; i < hours.Length; i++)
            Assert.Equal(TimeSpan.FromHours(hours[i]), clock.Delays[i]);
    }

    [Theory]
    [InlineData(0, 6.0)]
    [InlineData(1, 6.0)]   // 第一次失败仍按原节拍（退避从第二次失败起加码）
    [InlineData(2, 12.0)]
    [InlineData(3, 24.0)]
    [InlineData(9, 24.0)]  // 封顶：拉到「等于不再更新」就是新故障
    [InlineData(64, 24.0)] // 位移溢出边界：失败计数再大也只走封顶
    // 期望值写小时数而不是 "24:00:00"——TimeSpan.Parse 把首段 ≥24 当**天**
    // （实测 "24:00:00" == 24.00:00:00），字符串形态在这里会静默判错一个量级。
    public void NextDelay_backs_off_and_caps(int failures, double expectedHours) =>
        Assert.Equal(
            TimeSpan.FromHours(expectedHours),
            ThreatFeedCoordinator.NextDelay(TimeSpan.FromHours(6), failures));

    [Fact]
    public void NextDelay_leaves_a_disabled_cadence_alone()
    {
        // 节拍被显式关掉（≤0）时不该被退避改回正数——关闭周期本身是一个语义选择
        Assert.Equal(TimeSpan.Zero, ThreatFeedCoordinator.NextDelay(TimeSpan.Zero, 3));
        Assert.Equal(TimeSpan.FromMinutes(-5), ThreatFeedCoordinator.NextDelay(TimeSpan.FromMinutes(-5), 2));
    }

    [Fact]
    public async Task Periodic_loop_refetches_on_each_tick()
    {
        var clock = new FakeClock();
        var fetches = 0;
        var c = Build(() => "https://feeds.example/list.txt", (_, _) =>
        {
            fetches++;
            if (fetches >= 3) clock.Cancel.Cancel();
            return new[] { "tracker.example" };
        }, clock, Six);

        Assert.True(c.Start());
        await c.BackgroundTask!;

        // 首刷（Start）+ 两个节拍：节拍数恰为 2，每次都是默认 6 小时
        Assert.Equal(3, fetches);
        AssertDelays(clock, 6, 6);
        Assert.NotNull(c.LastSuccessUtc);
    }

    [Fact]
    public async Task Failures_back_off_and_a_success_resets_the_schedule()
    {
        var clock = new FakeClock();
        var fetches = 0;
        IReadOnlyList<string> Flaky(string _, string __)
        {
            fetches++;
            if (fetches is 2 or 3) throw new IOException("503");
            if (fetches >= 5) clock.Cancel.Cancel();
            return new[] { "tracker.example" };
        }
        var c = Build(() => "https://feeds.example/list.txt", Flaky, clock, Six);

        Assert.True(c.Start());
        await c.BackgroundTask!;

        // 6h（首成功后）→ 6h（第 1 次失败：退避从第二次起加码）→ 12h（第 2 次失败）
        // → 6h（第 3 次成功清零）：最后那一档就是「成功会复位退避」的证据
        AssertDelays(clock, 6, 6, 12, 6);
        Assert.Contains(_logs, l => l.Contains("第 1 次连续失败") && l.Contains("6 小时"));
        Assert.Contains(_logs, l => l.Contains("第 2 次连续失败") && l.Contains("12 小时"));
    }

    [Fact]
    public async Task Cleared_feed_means_no_further_network_activity_not_a_cleared_list()
    {
        // 「未配置源 ⇒ 零流量」在周期化之后必须是同一件事；而清空订阅源也绝不能顺手把
        // 已生效的名单清空——那等于用一个设置动作制造防护空窗。
        var clock = new FakeClock { CancelAfterTicks = 2 };
        var fetches = 0;
        string? url = "https://feeds.example/list.txt";
        var applied = new List<IBlockedHosts>();
        var c = new ThreatFeedCoordinator(
            applied.Add, _cachePath, () => url, _logs.Add,
            (_, _) => { fetches++; url = null; return new[] { "x.example" }; },
            Six, clock.Delay,
            () => new DateTimeOffset(2026, 10, 11, 12, 0, 0, TimeSpan.Zero),
            clock.Cancel.Token);

        Assert.True(c.Start());
        await c.BackgroundTask!;

        Assert.Equal(1, fetches);            // 清空之后的那一轮零网络活动
        Assert.Equal(2, applied.Count);      // 缓存快照 + 一次刷新，再没有第三次
        Assert.True(applied[^1].IsBlocked("x.example"));   // 名单保持生效，没被清空
    }

    [Fact]
    public async Task RefreshNow_respects_the_same_validation_as_the_loop()
    {
        var clock = new FakeClock();
        var fetches = 0;
        var invalid = Build(() => "http://feeds.example/list.txt",
            (_, _) => { fetches++; return Array.Empty<string>(); }, clock, TimeSpan.Zero);

        Assert.False(invalid.Start());
        await invalid.BackgroundTask!;       // 先收口再读 _logs（后台线程也在写它）
        Assert.False(invalid.RefreshNow());  // 非 https：既不启动周期也不立即刷
        Assert.Equal(0, fetches);
        Assert.Contains(_logs, l => l.Contains("订阅源非法"));
    }

    [Fact]
    public async Task RefreshNow_kicks_a_fetch_without_waiting_for_the_tick()
    {
        // 正向半边：只测负向半边（非法源）的话，「保存即刷新」把按钮接在死线上也全绿。
        // 节拍关掉（TimeSpan.Zero）⇒ 除 Start 的首刷与这里的立即刷，没有别的取源路径。
        var clock = new FakeClock();
        var fetches = 0;
        var c = Build(() => "https://feeds.example/list.txt",
            (_, _) => { fetches++; return new[] { "x.example" }; }, clock, TimeSpan.Zero);

        Assert.True(c.Start());
        await c.BackgroundTask!;
        Assert.Equal(1, fetches);

        Assert.True(c.RefreshNow());
        await WaitUntil(() => fetches >= 2);
        Assert.Equal(2, fetches);
    }

    [Fact]
    public async Task Concurrent_refreshes_are_serialised()
    {
        // Q52 新增第二条取源出口带来的竞态：周期循环与「保存即刷」并发时两个抓取各自
        // apply 一次，而后**完成**的那个决定最终名单——它可能是先发出那个请求的旧结果。
        // 去掉 _refreshGate 这条就红（overlap 变 1）。
        var clock = new FakeClock();
        var inside = 0;
        var overlaps = 0;
        var fetches = 0;
        var c = Build(() => "https://feeds.example/list.txt", (_, _) =>
        {
            fetches++;
            if (Interlocked.Exchange(ref inside, 1) == 1) Interlocked.Increment(ref overlaps);
            Thread.Sleep(50);   // 没有闸门时让两次重叠可观测
            Interlocked.Exchange(ref inside, 0);
            return new[] { "x.example" };
        }, clock, TimeSpan.Zero);

        Assert.True(c.Start());
        await c.BackgroundTask!;
        c.RefreshNow();
        c.RefreshNow();
        await WaitUntil(() => fetches >= 3);

        Assert.Equal(0, overlaps);
        Assert.Equal(3, fetches);
    }

    [Fact]
    public void Start_registers_the_active_coordinator_for_the_settings_window()
    {
        // 设置界面靠这个单点发起「保存即刷新」；它指错人就等于按钮没接线。
        // 能确定断言的前提是 Core.Tests 的 xunit.runner.json 关了集合并行
        // （parallelizeTestCollections:false）——将来打开并行，本类与其它调用
        // Start() 的类必须归进同一个 [Collection]。
        var clock = new FakeClock();
        var c = Build(() => null, (_, _) => Array.Empty<string>(), clock, TimeSpan.Zero);
        c.Start();
        Assert.True(ReferenceEquals(ThreatFeedCoordinator.Active, c));
    }

    private static async Task WaitUntil(Func<bool> condition, int timeoutMs = 5000)
    {
        var deadline = Environment.TickCount64 + timeoutMs;
        while (!condition())
        {
            if (Environment.TickCount64 > deadline)
                throw new TimeoutException("后台刷新链未在时限内推进（不得静默通过）");
            await Task.Delay(10);
        }
    }
}

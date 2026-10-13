namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Aegis.Windows.TestSupport;
using Xunit;

/// <summary>测试记录面的并发口径（R9-B54 / 台账 §五 Q62 = R9-CS-19）。
///
/// 起因是一条**偶发红**的 CI：`ThreatFeedCoordinatorTests.cs:65` 在 run 38461642255 红一条
/// `InvalidOperationException: Collection was modified; enumeration operation may not execute`，
/// 而同一 commit 的另外两个触发面全绿。红因不在被测对象，而在用例自己的记录面：写侧是
/// `ThreatFeedCoordinator` 的后台线程（`applyHosts` / `message` 两个回调），读侧是测试线程
/// 每 10ms 一轮的 `SpinUntil` 枚举——两边是同一个 `List<T>`。
///
/// 这类红灯的真实代价不是「一次失败」，而是它的处置方式：重跑一次就绿了，于是门禁每一次
/// 绿都少一分证据力（R9-CI 那批反复记的方向）。所以这里两层都判：
/// - 行为层：并发记入 + 并发枚举必须不抛，且一条不丢、不重复；读侧与写侧的**重叠**是
///   协调出来的（读线程先报到，写线程才开工），否则这条用例可以空跑而全绿；
/// - 接线层：那三处已知字段必须是带锁快照面、且不得再出现 `.Add(` 的写法——改回 `List<T>`
///   最容易发生在解合并冲突的时候，而那时没人会把它和 CI 的偶发红联系起来。
///
/// **一条刻意没写的断言**：不判「普通 `List<T>` 在这种并发下必抛」。那个断言本身就是竞态
/// （它可能不抛），把它写成用例等于再造一条偶发红灯。实测形态记在台账 §3.54。
///
/// 本批自己也被这条判据教了一次：第一版用 `Task.Run` 起读线程 + 固定 2000 圈的自旋上限，
/// CI（2 核 runner）上红在「与写侧根本没有重叠」——自旋读线程占着线程池 worker，写任务排在
/// 后面，读线程却已经把圈数烧完退场了。**非空心断言当场把一件设计缺陷变成了红灯**，
/// 这正是它存在的意义（第二版改用专用线程 + 「写侧真的结束」作为退出条件，见下面的注释）。</summary>
public sealed class ThreadSafeRecorderTests
{
    private const int Writers = 8;
    private const int PerWriter = 400;
    private const int Readers = 4;
    private const int HandshakeSeconds = 30;

    [Fact]
    public void Concurrent_record_and_enumerate_never_throw()
    {
        // 用专用线程而不是 Task.Run：读侧是自旋的，占着线程池 worker，而 8 个写任务排在
        // 后面——2 核 runner 上实测就是这么红的（run 38469671504 先炸的是「与写侧根本没有
        // 重叠」那条非空心断言）。重叠必须由**构造**保证，不能交给调度器的心情。
        var rec = new ThreadSafeRecorder<int>();
        var failures = new List<Exception>();
        var reads = 0;
        var nonEmptyReads = 0;
        var enumeratedItems = 0;
        var writersFinished = 0;
        var seeded = 0;
        using var readersReady = new CountdownEvent(Readers);
        using var writersDone = new ManualResetEventSlim(false);

        var readers = Enumerable.Range(0, Readers).Select(slot =>
        {
            var thread = new Thread(() =>
            {
                try
                {
                    readersReady.Signal();
                    var deadline = Environment.TickCount64 + HandshakeSeconds * 1000;
                    do
                    {
                        var snapshot = rec.Snapshot();
                        Interlocked.Increment(ref reads);
                        if (snapshot.Length > 0) Interlocked.Increment(ref nonEmptyReads);
                        _ = snapshot.Any(v => v % 7 == 0);      // LINQ 链：CI 上真实那一句的形态
                        _ = rec.Count;                            // 计数面
                        var counted = 0;
                        foreach (var _ in rec) counted++;          // 直接枚举（xunit 断言走这条）
                        Interlocked.Add(ref enumeratedItems, counted);
                    }
                    // 收工条件是「写侧真的结束」，不是「我转了几千圈」：后者在慢 runner 上
                    // 会先烧完，于是这条用例又变成空跑。
                    while (!writersDone.IsSet && Environment.TickCount64 < deadline);
                }
                catch (Exception e)
                {
                    lock (failures) failures.Add(e);
                }
            })
            { IsBackground = true };
            thread.Start();
            return thread;
        }).ToArray();

        var writers = Enumerable.Range(0, Writers).Select(batch =>
        {
            var thread = new Thread(() =>
            {
                try
                {
                    if (!readersReady.Wait(TimeSpan.FromSeconds(HandshakeSeconds)))
                        throw new TimeoutException("读线程没报到——这条用例的并发面根本没建立起来");
                    var from = 0;
                    if (batch == 0)
                    {
                        // 种子写 + 反向握手：先让记录面非空，再等**读线程确实读到过非空快照**，
                        // 其余写入才开工。nonEmptyReads>0 因此是构造出来的事实，不是运气。
                        rec.Record(0);
                        from = 1;
                        var deadline = Environment.TickCount64 + HandshakeSeconds * 1000;
                        while (Volatile.Read(ref nonEmptyReads) == 0)
                        {
                            if (Environment.TickCount64 > deadline)
                                throw new TimeoutException("种子写之后没有任何一次非空读取：读线程没在并发跑");
                            Thread.SpinWait(64);
                        }
                        Volatile.Write(ref seeded, 1);
                    }
                    else
                    {
                        var deadline = Environment.TickCount64 + HandshakeSeconds * 1000;
                        while (Volatile.Read(ref seeded) == 0)
                        {
                            if (Environment.TickCount64 > deadline)
                                throw new TimeoutException("种子写线程没走完握手");
                            Thread.SpinWait(64);
                        }
                    }
                    for (var i = from; i < PerWriter; i++) rec.Record(batch * PerWriter + i);
                    if (Interlocked.Increment(ref writersFinished) == Writers) writersDone.Set();
                }
                catch (Exception e)
                {
                    lock (failures) failures.Add(e);
                    writersDone.Set();   // 别让读线程陪着挂
                }
            })
            { IsBackground = true };
            thread.Start();
            return thread;
        }).ToArray();

        foreach (var thread in writers)
        {
            if (!thread.Join(TimeSpan.FromSeconds(HandshakeSeconds * 2)))
                throw new TimeoutException("写线程没在时限内收工");
        }
        writersDone.Set();
        foreach (var thread in readers)
        {
            if (!thread.Join(TimeSpan.FromSeconds(HandshakeSeconds)))
                throw new TimeoutException("读线程没在时限内收工");
        }

        Assert.True(failures.Count == 0,
            string.Join(" | ", failures.Select(f => $"{f.GetType().Name}: {f.Message}")));
        Assert.Equal(Writers, Volatile.Read(ref writersFinished));
        Assert.Equal(Writers * PerWriter, rec.Count);
        var all = rec.Snapshot();
        Assert.Equal(Writers * PerWriter, all.Length);
        Assert.Equal(all.Length, all.Distinct().Count());   // 没丢也没重复
        Assert.True(reads >= Readers, $"读线程每人至少跑一轮：实得总轮数 {reads}");
        Assert.True(nonEmptyReads > 0, "读线程从没读到过任何内容：与写侧根本没有重叠");
        Assert.True(enumeratedItems > 0, "直接枚举一条内容都没产出：与写侧根本没有重叠");
    }


    [Fact]
    public void Snapshot_is_a_standalone_view_not_a_live_window()
    {
        // 正向控制：拿到快照后继续写，已拿到的视图不变。这条钉的是「调用方可以在同一份视图上
        // 跑完整条链」——也就是不抛的那个前提，而不只是测「没抛」。
        var rec = new ThreadSafeRecorder<string>();
        rec.Record("first");
        var before = rec.Snapshot();
        rec.Record("second");
        Assert.Single(before);
        Assert.Equal("first", before[0]);
        Assert.Equal(2, rec.Count);
    }

    [Fact]
    public void Indexer_reads_a_stable_position_not_a_live_cursor()
    {
        // 已知读法：`LastApplied(h) => h.Applied[^1]`、`_pushed[0]`、`_pushed[^1]`
        // ——这些断言靠的就是顺序，所以按位置取这一面必须留着。
        var rec = new ThreadSafeRecorder<int>();
        rec.Record(1);
        rec.Record(2);
        Assert.Equal(1, rec[0]);
        Assert.Equal(2, rec[^1]);
    }

    // ===== 接线锚：那三处记录字段不得改回普通 List =====

    /// <summary>被观察的三处字段（相对 `windows/tests` 的路径 → 声明里必须出现的样子）。</summary>
    private static readonly (string Relative, string Declaration)[] KnownRecorders =
    [
        (@"Aegis.Windows.Core.Tests\ThreatFeedCoordinatorTests.cs", "ThreadSafeRecorder<IBlockedHosts> Applied"),
        (@"Aegis.Windows.Core.Tests\ThreatFeedCoordinatorTests.cs", "ThreadSafeRecorder<string> Logs"),
        (@"Aegis.Windows.Broker.Tests\CoreDenylistPublisherTests.cs",
         "ThreadSafeRecorder<IReadOnlyCollection<string>> _pushed"),
    ];

    private static readonly string[] RecorderNames = ["Applied", "Logs", "_pushed"];

    /// <summary>纯函数：给定一个测试文件的**代码**（已剔注释），返回记录面问题。
    /// 内存态注入走同一份判定，反向锚才落在真逻辑上（`OutOfBandFetchDisciplineTests` 同口径）。</summary>
    private static List<string> RecorderProblems(string code)
    {
        var problems = new List<string>();
        foreach (var name in RecorderNames)
        {
            if (code.Contains($"{name}.Add(", StringComparison.Ordinal))
                problems.Add($"{name}.Add( 又回来了——写侧换了线程就会与测试线程的枚举撞车");
        }
        return problems;
    }

    [Fact]
    public void Known_recorder_fields_are_the_guarded_type()
    {
        foreach (var (relative, declaration) in KnownRecorders)
        {
            var code = SourceTextAnchors.CodeOnly(ReadTestSource(relative));
            Assert.True(code.Contains(declaration, StringComparison.Ordinal),
                $"{relative} 的记录面不再是 {declaration}——Q62 那次偶发红灯会回来");
            Assert.Empty(RecorderProblems(code));
        }
    }

    [Fact]
    public void An_injected_plain_list_recorder_is_red()
    {
        // 上一条里那个 Empty 断言的正面控制：同一份判定必须认得被禁形态，否则它恒真。
        var injected = "public readonly List<IBlockedHosts> Applied = new();\n" +
                       "void Build() => Start(applyHosts: applied => Applied.Add(applied));";
        var problems = RecorderProblems(SourceTextAnchors.CodeOnly(injected));
        Assert.Single(problems);
        Assert.Contains("Applied", problems[0], StringComparison.Ordinal);
    }

    /// <summary>从测试输出上溯到 `windows/tests`（CI 与本地同形：跑测试前必然 checkout）。</summary>
    private static string ReadTestSource(string relative)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "windows", "tests", relative);
            if (File.Exists(candidate)) return File.ReadAllText(candidate);
            dir = dir.Parent;
        }
        throw new InvalidOperationException($"未从测试输出上溯到 windows/tests/{relative}——布局变了就改这里");
    }
}

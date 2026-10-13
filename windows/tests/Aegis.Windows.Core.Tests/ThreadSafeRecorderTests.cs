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
/// （它可能不抛），把它写成用例等于再造一条偶发红灯。实测形态记在台账 §3.54。</summary>
public sealed class ThreadSafeRecorderTests
{
    private const int Writers = 8;
    private const int PerWriter = 400;
    private const int Readers = 4;
    private const int ReadSpins = 2_000;

    [Fact]
    public async Task Concurrent_record_and_enumerate_never_throw()
    {
        var rec = new ThreadSafeRecorder<int>();
        var reads = 0;
        var nonEmptyReads = 0;
        var enumeratedTotal = 0;
        var writersFinished = 0;
        var readersReady = new CountdownEvent(Readers);
        var writersDone = 0;

        // 读侧三种形态都要跑到：整条 LINQ 链（CI 上真实的那一句）、Count、foreach。
        // 任一环节抛 InvalidOperationException 都会从 await 里传出来。
        var readTasks = Enumerable.Range(0, Readers).Select(slot => Task.Run(() =>
        {
            readersReady.Signal();
            var spin = 0;
            while (spin < ReadSpins && Volatile.Read(ref writersDone) == 0)
            {
                Interlocked.Increment(ref reads);
                var snapshot = rec.Snapshot();
                if (snapshot.Length > 0) Interlocked.Increment(ref nonEmptyReads);
                _ = snapshot.Any(v => v % 7 == 0);          // LINQ 链：CI 上真实的那一句
                _ = rec.Count;                                // 计数面
                var sum = 0;
                foreach (var value in rec) sum += value % 3;  // 直接枚举（xunit 断言走的就是这条）
                Interlocked.Add(ref enumeratedTotal, sum);
                spin++;
            }
        })).ToArray();

        // 重叠是协调出来的：写线程必须等读线程报到之后才开工——反过来这条用例就可能
        // 在「没人并发」的时刻跑完，绿得毫无意义（空心门禁，R9-B39 同一课）。
        var writeTasks = Enumerable.Range(0, Writers).Select(batch => Task.Run(() =>
        {
            if (!readersReady.Wait(TimeSpan.FromSeconds(30)))
                throw new TimeoutException("读线程没报到——这条用例的并发面根本没建立起来");
            for (var i = 0; i < PerWriter; i++) rec.Record(batch * PerWriter + i);
            // 最后一名写线程收工才叫结束：读线程必须至少与一段写入真正重叠过。
            if (Interlocked.Increment(ref writersFinished) == Writers) Volatile.Write(ref writersDone, 1);
        })).ToArray();

        await Task.WhenAll(readTasks.Concat(writeTasks)).WaitAsync(TimeSpan.FromSeconds(60));

        Assert.Equal(Writers, Volatile.Read(ref writersFinished));
        Assert.Equal(Writers * PerWriter, rec.Count);
        var all = rec.Snapshot();
        Assert.Equal(Writers * PerWriter, all.Length);
        Assert.Equal(all.Length, all.Distinct().Count());   // 没丢也没重复
        Assert.True(reads > 0, "读线程一次都没跑到——判据在判空气");
        Assert.True(nonEmptyReads > 0, "读线程从没读到过任何内容：与写侧根本没有重叠");
        Assert.True(enumeratedTotal > 0, "直接枚举一条内容都没产出：与写侧根本没有重叠");
        readersReady.Dispose();
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

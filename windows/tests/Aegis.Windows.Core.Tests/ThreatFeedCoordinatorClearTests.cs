namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Aegis.Windows.Core.Security;
using Aegis.Windows.TestSupport;
using Xunit;

/// <summary>R9-B86（队列 Q54，用户定「清空即解除」）：`ClearAndDisableAsync` 的行为面。
///
/// 为什么单独成文件而不是塞进 ThreatFeedCoordinatorTests：那份文件已在 221 行，加这三条会撞
/// SP-255 的 300 行红线（实测 306 行被 `check_file_sizes.py` 判红，CI 现读）。本仓的既有处理
/// 办法是按职责拆文件而不是抬红线或压用例（同款见 gradle 校验和那族按「配置面/重算面」拆两份）。
///
/// 三条各钉一件事：①清空确实把内存名单解除并删缓存；②**在途抓取晚于清空完成时最终态仍是解除**
/// ——这条是本批的存在理由，不持闸的实现能让①也全绿；③删除失败不回退解除、但必须留痕。
/// 记录面一律走 ThreadSafeRecorder（写侧是协调器的后台线程，读侧是测试线程的 SpinUntil 枚举——
/// 普通 List 在这个读法下抛 Collection was modified，台账 §五 Q62 记过一次偶发红灯）。</summary>
public sealed class ThreatFeedCoordinatorClearTests : IDisposable
{
    private readonly string _cachePath =
        Path.Combine(Path.GetTempPath(), $"aegis_threat_clear_{Guid.NewGuid():N}.txt");

    private sealed class Harness
    {
        public readonly ThreadSafeRecorder<IBlockedHosts> Applied = new();
        public readonly ThreadSafeRecorder<string> Logs = new();
        public string? FeedUrl = "https://feeds.example/list.txt";
        public string[] FetchedCacheContents = ["refreshed.example"];
        public List<string?> Deleted = new();
        public Func<string, string, IReadOnlyList<string>>? Fetch;
        public Action<string>? Delete;

        public ThreatFeedCoordinator Build(string cachePath) =>
            new(
                applyHosts: applied => Applied.Record(applied),
                cachePath,
                () => FeedUrl,
                message => Logs.Record(message),
                fetchAndStore: Fetch ?? ((url, cache) =>
                {
                    File.WriteAllLines(cache, FetchedCacheContents);
                    return FetchedCacheContents;
                }),
                refreshInterval: TimeSpan.Zero,   // 本类只测「清空」那一条链，节拍关掉
                deleteCache: Delete ?? (path => Deleted.Add(path)));
    }

    [Fact]
    public async System.Threading.Tasks.Task Clear_releases_the_list_and_deletes_the_cache()
    {
        // 清空要同时做掉两件事：内存里那份名单解除、缓存文件删掉。
        // 少做后半件的后果不是「留个垃圾文件」而是下次启动 `Start()` 无条件 LoadCached
        // 又把旧名单装回来——那正是 Q54 登记的原缺陷。
        File.WriteAllLines(_cachePath, ["doubleclick.net"]);
        var h = new Harness();
        var c = h.Build(_cachePath);
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        Assert.True(await c.ClearAndDisableAsync());
        await SettleAsync(c);
        Assert.Equal(_cachePath, Assert.Single(h.Deleted));
        Assert.False(h.Applied[^1].IsBlocked("doubleclick.net"));
        Assert.Contains(h.Logs, l => l.Contains("黑名单已解除"));
        Assert.Contains(h.Logs, l => l.Contains("缓存文件已删除"));
    }

    [Fact]
    public async System.Threading.Tasks.Task Clear_beats_an_inflight_refresh_on_the_final_state()
    {
        // 本批唯一真正的性质测试：清空必须**排在**在途抓取之后生效。
        // ClearAndDisableAsync 持着 _refreshGate，所以它会等这次抓取落定再 apply 空名单。
        // 哪天有人去掉那道闸（或把清空改成前插、不等），旧名单会后到把 doubleclick 装回来：
        // 用户按了「清空」、也看到了那句提示，防护却还在线上——Q54 反过来发作。
        var gate = new System.Threading.Tasks.TaskCompletionSource();
        var h = new Harness { FetchedCacheContents = ["late-block.example"] };
        h.Fetch = (_, cache) =>
        {
            File.WriteAllLines(cache, h.FetchedCacheContents);
            if (!gate.Task.Wait(3000))
                throw new TimeoutException("在途抓取没等到放行：这条用例的窗口没走通");
            return h.FetchedCacheContents;
        };
        File.WriteAllLines(_cachePath, ["doubleclick.net"]);
        var c = h.Build(_cachePath);
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        h.FeedUrl = null;                    // 模拟设置页清空后：解析不到源
        var clearing = c.ClearAndDisableAsync();
        gate.SetResult();                    // 让那次「先发出、后完成」的抓取跑完
        Assert.True(await clearing);
        await SettleAsync(c);
        // 非空心判据：快照 + 迟到的刷新 + 清空三次应用都发生，才算真踩到那个窗口；
        // 少了任何一次，这条断言就在判一个根本没执行的分支（恒绿）。
        Assert.True(h.Applied.Count >= 3, $"只应用了 {h.Applied.Count} 次：竞态窗口没走到");
        Assert.False(h.Applied[^1].IsBlocked("late-block.example"));
        Assert.False(h.Applied[^1].IsBlocked("doubleclick.net"));
    }

    [Fact]
    public async System.Threading.Tasks.Task Clear_with_a_failing_delete_still_releases_the_list()
    {
        // 方向要说清：删除失败**不回退**解除。用户要的「关掉」已当场生效，
        // 残留一个缓存文件是可诊断的小问题——但它意味着重启会重新加载，所以必须留痕。
        File.WriteAllLines(_cachePath, ["doubleclick.net"]);
        var h = new Harness
        {
            Delete = _ => throw new IOException("used by another process"),
        };
        var c = h.Build(_cachePath);
        Assert.True(c.Start());
        await SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(b => b.IsBlocked("doubleclick.net")));
        Assert.False(await c.ClearAndDisableAsync());
        await SettleAsync(c);
        Assert.False(h.Applied[^1].IsBlocked("doubleclick.net"));
        Assert.Contains(h.Logs, l => l.Contains("黑名单已解除"));
        Assert.Contains(h.Logs, l => l.Contains("重启后仍会从该文件加载"));
    }

    private static async System.Threading.Tasks.Task SpinUntil(Func<bool> condition, int timeoutMs = 4000)
    {
        var deadline = Environment.TickCount64 + timeoutMs;
        while (!condition())
        {
            if (Environment.TickCount64 > deadline)
                throw new TimeoutException("后台任务未在时限内完成");
            await System.Threading.Tasks.Task.Delay(10);
        }
    }

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
            // 也不让清理动作把已经通过的用例反手打红（同款处理见 ThreatFeedCoordinatorTests）。
        }
    }
}

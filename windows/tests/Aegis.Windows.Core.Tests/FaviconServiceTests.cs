namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Favicons;
using Xunit;

/// <summary>C9 批（审计 2026-09-26）：favicon 磁盘缓存路径形态直测（CS-120）。
/// 仅路径计算无 IO——AppPaths 指向真实用户目录也不落盘。
/// C19b 批（审计 2026-09-26）：CS-328 进程级缓存面（负缓存命中短路按
/// 持久化语境分面/InFlight 去重/TrimCaches 上限）经 internal 可测缝 + 抓取桩覆盖。</summary>
public sealed class FaviconServiceTests : IDisposable
{
    [Fact]
    public void CachePathNormalizesHostCase()
    {
        // host 大小写归一——同站点命中同一磁盘文件
        Assert.Equal(
            FaviconService.CachePath("Example.COM"),
            FaviconService.CachePath("example.com"));
    }

    [Fact]
    public void CachePathIsSha1HexPngName()
    {
        // 40 位大写十六进制哈希 + .png 后缀——host 不直接进文件名（路径注入面）
        var path = FaviconService.CachePath("example.com");
        Assert.EndsWith(".png", path);
        var name = Path.GetFileNameWithoutExtension(path);
        Assert.Equal(40, name.Length);
        Assert.Matches("^[0-9A-F]{40}$", name);
    }

    // ===== CS-356（2026-10-01 审计）：IPv6 host 抓取 URL 构造 =====

    [Theory]
    [InlineData("example.com", "https://example.com/favicon.ico")]
    [InlineData("sub.example.com", "https://sub.example.com/favicon.ico")]
    [InlineData("::1", "https://[::1]/favicon.ico")]                    // 无方括号形态补括号
    [InlineData("[2001:db8::1]", "https://[2001:db8::1]/favicon.ico")]  // 已带括号不双包
    [InlineData("2001:db8::1:8443", "https://[2001:db8::1:8443]/favicon.ico")]
    public void BuildFaviconUrl_BracketsIpv6Literals(string host, string expected)
    {
        // IPv6 host 无方括号直接拼接产生非法 URL——永远失败并进负缓存；
        // host 含 ':' 时按 RFC 3986 补方括号
        Assert.Equal(expected, FaviconService.BuildFaviconUrl(host));
    }

    // ===== C19b 批：CS-328（桩注入——确定性驱动异步路径） =====

    public FaviconServiceTests()
    {
        FaviconService.ClearCachesForTests();
    }

    public void Dispose()
    {
        FaviconService.FetchHookForTests = null;
        FaviconService.ClearCachesForTests();
    }

    /// <summary>等待 in-flight 抓取结束（桩完成 + 移除）——确定性收敛。</summary>
    private static async Task WaitForFlightSettleAsync(string host, bool persistToDisk)
    {
        for (var i = 0; i < 200; i++)
        {
            if (!FaviconService.IsInFlight(host, persistToDisk))
                return;
            await Task.Delay(10);
        }
    }

    [Fact]
    public async Task NegativeCache_IsScopedByPersistenceContext()
    {
        // CS-309/328：无痕语境抓取失败的负缓存不得短路普通语境——此前 Miss
        // 只按 host（进程级共享），普通窗口首访直接命中负缓存不抓取
        var host = $"miss-scope-{Guid.NewGuid():N}.invalid";
        var gate = new TaskCompletionSource<System.Windows.Media.ImageSource?>();
        FaviconService.FetchHookForTests = _ => gate.Task;

        _ = FaviconService.Get(host, onLoaded: null, persistToDisk: false);
        gate.SetResult(null);  // 抓取失败
        await WaitForFlightSettleAsync(host, persistToDisk: false);

        Assert.True(FaviconService.IsMissCached(host, persistToDisk: false));
        Assert.False(FaviconService.IsMissCached(host, persistToDisk: true),
            "无痕语境的负缓存不得泄漏到普通语境");
    }

    [Fact]
    public async Task InFlight_SameHostConcurrentGets_AreDeduplicated()
    {
        // CS-328：同 host 并发首取只发起一次抓取（in-flight 去重）——
        // 抓取桩计数锁定 GetOrAdd 工厂只执行一次
        var host = $"dedupe-{Guid.NewGuid():N}.invalid";
        var gate = new TaskCompletionSource<System.Windows.Media.ImageSource?>();
        var fetchCount = 0;
        FaviconService.FetchHookForTests = _ =>
        {
            fetchCount++;
            return gate.Task;
        };

        _ = FaviconService.Get(host, onLoaded: null, persistToDisk: true);
        _ = FaviconService.Get(host, onLoaded: null, persistToDisk: true);
        _ = FaviconService.Get(host, onLoaded: null, persistToDisk: true);
        Assert.True(FaviconService.IsInFlight(host, persistToDisk: true));

        gate.SetResult(null);
        await WaitForFlightSettleAsync(host, persistToDisk: true);
        Assert.False(FaviconService.IsInFlight(host, persistToDisk: true));
        Assert.Equal(1, fetchCount);  // 三次并发首取 → 一次真实抓取
    }

    [Fact]
    public async Task TrimCaches_BoundsMissCache()
    {
        // CS-328：负缓存上限——超 MaxMemoryEntries 触发清空（Miss.Clear）
        var host = $"trim-{Guid.NewGuid():N}.invalid";
        var gate = new TaskCompletionSource<System.Windows.Media.ImageSource?>();
        FaviconService.FetchHookForTests = _ => gate.Task;
        // 预置 501 条负缓存（超过 500 上限——批量预置经测试缝）
        for (var i = 0; i < 501; i++)
            FaviconService.SeedMissForTests($"pre-{i}.example", persistToDisk: true);

        _ = FaviconService.Get(host, onLoaded: null, persistToDisk: false);
        gate.SetResult(null);  // miss → TrimCaches → Miss.Clear()
        await WaitForFlightSettleAsync(host, persistToDisk: false);

        Assert.True(FaviconService.MissCount <= 1,
            $"超限后负缓存应被清空（实际 {FaviconService.MissCount}）");
    }
}

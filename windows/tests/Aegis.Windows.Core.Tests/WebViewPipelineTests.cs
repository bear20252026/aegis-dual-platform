namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using System.Linq;
using Aegis.Windows.Core;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>C21 批（2026-10-01 审计）：WebView 封装层提纯逻辑直测——
/// CS-362 HTTPS-only 升级 URL 构造、CS-363 拦截聚合（聚合/阈值/尾部清空）、
/// CS-339 帧路径本机判定只读缓存、CS-352 无痕临时目录孤儿清理。</summary>
public sealed class HostWebViewLogicTests
{
    // ===== CS-362：BuildHttpsUpgradeUrl =====

    [Theory]
    [InlineData("http://example.com/a/b?q=1#frag", "https://example.com/a/b?q=1")]
    [InlineData("http://example.com:8080/x", "https://example.com:8080/x")]
    [InlineData("http://example.com", "https://example.com/")]
    public void BuildHttpsUpgradeUrl_KeepsHostPortPathQuery_DropsFragment(string raw, string expected)
    {
        var uri = new Uri(raw);
        Assert.Equal(expected, HostWebView.BuildHttpsUpgradeUrl(uri));
    }

    [Fact]
    public void BuildHttpsUpgradeUrl_DropsUserinfo()
    {
        // userinfo 随升级一并剥离——凭据不进入升级后的导航地址
        var uri = new Uri("http://token@example.com/p?q=1");
        Assert.Equal("https://example.com/p?q=1", HostWebView.BuildHttpsUpgradeUrl(uri));
    }

    // ===== CS-363：TrackerBlockAggregator =====

    [Fact]
    public void TrackerAggregator_AggregatesPerHost_AndReturnsTrueAtThreshold()
    {
        var aggregator = new TrackerBlockAggregator(flushThreshold: 3);

        Assert.False(aggregator.Record("ads.example", "级别2 ctx=Script"));
        Assert.False(aggregator.Record("ads.example", "级别2 ctx=Fetch"));  // 同 host 聚合
        Assert.True(aggregator.Record("tracker.example", "级别2 ctx=Image"));

        var rows = aggregator.Drain();
        Assert.Equal(2, rows.Count);
        var ads = Assert.Single(rows, r => r.Host == "ads.example");
        Assert.Equal(2, ads.Count);
        Assert.Equal("级别2 ctx=Script", ads.Detail);  // detail 取首次形态
        Assert.Equal(0, aggregator.PendingCount);
    }

    [Fact]
    public void TrackerAggregator_DrainResetsCounters_TailFlushIsEmpty()
    {
        // Dispose 兜底：未满阈值的尾部聚合 Drain 一次取走，二次为空
        var aggregator = new TrackerBlockAggregator(flushThreshold: 50);
        aggregator.Record("ads.example", "d");

        var first = aggregator.Drain();
        Assert.Single(first);
        Assert.Equal(0, aggregator.PendingCount);
        Assert.Empty(aggregator.Drain());
    }

    // ===== CS-339：帧路径本机判定只读缓存 =====

    [Theory]
    [InlineData("localhost", true)]
    [InlineData("LOCALHOST", true)]
    [InlineData("dev.localhost", true)]
    [InlineData("localhost.", true)]      // 尾点归一后命中
    [InlineData("127.0.0.1", true)]
    [InlineData("169.254.10.9", false)]   // 链路本地是 IP 但非本机——有确定判定
    public void TryGetCachedLocalHost_ExplicitNamesAndIps_ResolveWithoutDns(string host, bool expectedLocal)
    {
        // 显式本机名/回环 IP/非回环 IP：不需要 DNS 即可判定（返回 true=有判定）
        Assert.True(UrlSafety.TryGetCachedLocalHost(host, out var isLocal));
        Assert.Equal(expectedLocal, isLocal);
    }

    [Fact]
    public void TryGetCachedLocalHost_UnknownHost_ReturnsFalseWithoutDns()
    {
        // CS-339：未命中缓存返回 false——绝不在此发起同步 DNS（帧路径防
        // UI 冻结的核心契约）；调用方 fail-closed 取消 + 后台预热
        Assert.False(UrlSafety.TryGetCachedLocalHost(
            $"never-resolved-{Guid.NewGuid():N}.aegis.invalid", out _));
    }

    [Fact]
    public void TryGetCachedLocalHost_SeededCacheHit_ReturnsCachedVerdict()
    {
        // 后台预热（IsLocalHostOrResolvesLocalHost）落缓存后，下一次只读探测
        // 命中——帧导航恢复 hosts 本地域名放行语义
        var host = $"seeded-{Guid.NewGuid():N}.aegis.invalid";
        UrlSafety.SeedLocalHostCacheForTests(host, isLocal: true);
        Assert.True(UrlSafety.TryGetCachedLocalHost(host, out var isLocal));
        Assert.True(isLocal);
    }

    // ===== CS-382/388（2026-10-02 审计）：顶层 HTTPS-only 升级豁免 =====

    [Theory]
    [InlineData("192.168.1.1", true)]      // 内网 IP 字面量——豁免（保持 http）
    [InlineData("10.0.0.5", true)]
    [InlineData("172.16.4.9", true)]
    [InlineData("169.254.7.7", true)]      // 链路本地
    [InlineData("127.0.0.1", true)]        // 回环
    [InlineData("localhost", true)]
    [InlineData("dev.localhost", true)]
    [InlineData("printer.internal", true)] // 内网域名后缀（IsPublicHost 判非公网）
    [InlineData("nas.local", true)]
    public void IsExemptFromHttpsUpgrade_NonPublicHostsStayHttp(string host, bool expected)
    {
        // CS-388：裸内网 IP 被 UrlNormalizer 补 http:// 后又被升级炸掉的口径
        // 互斥——非公网主机一律豁免升级（纯同步判定，无 DNS）
        Assert.Equal(expected, HostWebView.IsExemptFromHttpsUpgrade(host));
    }

    [Fact]
    public void IsExemptFromHttpsUpgrade_PublicHost_ColdCacheFailsClosedToUpgrade()
    {
        // CS-382：公网域名冷缓存按非本机 fail-closed（本次升级 https）——
        // 判定纯同步，绝不在此发起 UI 线程 DNS（与帧路径 CS-339 口径统一）
        Assert.False(HostWebView.IsExemptFromHttpsUpgrade(
            $"public-{Guid.NewGuid():N}.aegis.example"));
    }

    [Fact]
    public void IsExemptFromHttpsUpgrade_SeededLocalHost_CacheHitExempts()
    {
        // CS-382：后台预热缓存命中后，hosts 映射到本机的域名恢复放行
        //（不升级——本地开发 http 场景）
        var host = $"upgrade-seeded-{Guid.NewGuid():N}.aegis.invalid";
        UrlSafety.SeedLocalHostCacheForTests(host, isLocal: true);
        Assert.True(HostWebView.IsExemptFromHttpsUpgrade(host));
    }
}

/// <summary>CS-352（2026-10-01 审计）：崩溃残留无痕临时目录启动清理。</summary>
public sealed class WebViewEnvironmentCleanupTests
{
    [Fact]
    public void CleanupOrphanInPrivateDirs_RemovesOnlyUnheldAegisDirs()
    {
        var root = Path.Combine(Path.GetTempPath(), $"aegis_ipcleanup_{Guid.NewGuid():N}");
        Directory.CreateDirectory(Path.Combine(root, "Aegis.InPrivate.aaa"));
        Directory.CreateDirectory(Path.Combine(root, "Aegis.InPrivate.bbb"));
        Directory.CreateDirectory(Path.Combine(root, "unrelated.dir"));
        var held = Path.Combine(root, "Aegis.InPrivate.held");
        Directory.CreateDirectory(held);
        try
        {
            // 登记为"本进程在用"——清理必须跳过（存活无痕窗口的数据目录）
            WebViewEnvironment.RegisterInPrivateDirForTests(held);

            var removed = WebViewEnvironment.CleanupOrphanInPrivateDirs(root);

            Assert.Equal(2, removed);
            Assert.False(Directory.Exists(Path.Combine(root, "Aegis.InPrivate.aaa")));
            Assert.False(Directory.Exists(Path.Combine(root, "Aegis.InPrivate.bbb")));
            Assert.True(Directory.Exists(held));                 // 在用目录保留
            Assert.True(Directory.Exists(Path.Combine(root, "unrelated.dir")));  // 非本应用目录不动
        }
        finally
        {
            WebViewEnvironment.UnregisterInPrivateDirForTests(held);
            try { Directory.Delete(root, true); } catch (IOException) { }
        }
    }

    [Fact]
    public void CleanupOrphanInPrivateDirs_MissingRoot_ReturnsZero()
    {
        var missing = Path.Combine(Path.GetTempPath(), $"aegis_no_such_{Guid.NewGuid():N}");
        Assert.Equal(0, WebViewEnvironment.CleanupOrphanInPrivateDirs(missing));
    }
}

/// <summary>R8-CS-SEC-02（第八轮 2026-10-05，B4 余量）：导航授权链的失败闭合边界。
///
/// 原形态 `e.Cancel = !TryAuthorizeNavigation(...)` 没有异常边界——求值期任何抛出
/// （桥租约、确认面板/拒绝提示的事件订阅方、URL 解析）都让整句赋值作废，`e.Cancel`
/// 停在默认 false ⇒ WebView2 照常导航。这与「导航默认拒绝」红线相反，属第八轮
/// §十一 队列里最值得先复核的那条（本轮逐行回读后确证为 P1 形态的门禁失效）。
/// handler 本体要 COM 对象，故把判定核抽成 internal 纯函数在此直测。</summary>
public sealed class NavigationFailClosedBoundaryTests : IDisposable
{
    private readonly string _logDir =
        Path.Combine(Path.GetTempPath(), $"aegis_navfail_{Guid.NewGuid():N}");

    public NavigationFailClosedBoundaryTests()
    {
        Directory.CreateDirectory(_logDir);
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = _logDir;
    }

    public void Dispose()
    {
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(_logDir, true); } catch (IOException) { }
    }

    [Fact]
    public void Authorized_predicateResultPassesThrough() =>
        Assert.True(HostWebView.IsAuthorizedFailClosed(() => true, "顶层导航"));

    [Fact]
    public void Unauthorized_returnsFalseSoHandlerCancels() =>
        Assert.False(HostWebView.IsAuthorizedFailClosed(() => false, "顶层导航"));

    /// <summary>本条就是这个修复的全部意义：求值期抛出不得等于「放行」。
    /// 取真实出现过的四类抛出面（桥租约/COM/会话/dispose 竞态），不用
    /// AccessViolationException——.NET Core 默认不可捕获，会把测试宿主一起带走。</summary>
    [Fact]
    public void AnyExceptionDuringAuthorization_IsTreatedAsUnauthorized()
    {
        Assert.False(HostWebView.IsAuthorizedFailClosed(
            () => throw new InvalidOperationException("原生桥租约已失效"), "顶层导航"));
        Assert.False(HostWebView.IsAuthorizedFailClosed(
            () => throw new NullReferenceException(), "子帧"));
        Assert.False(HostWebView.IsAuthorizedFailClosed(
            () => throw new ObjectDisposedException("CoreWebView2"), "顶层导航"));
        Assert.False(HostWebView.IsAuthorizedFailClosed(
            () => throw new System.Runtime.InteropServices.ExternalException(
                unchecked((int)0x80070005), "COM 拒绝"), "子帧"));
    }

    [Fact]
    public void AuthorizationException_IsRecordedNotSwallowedSilently()
    {
        // 留痕面：抛出必须落安全日志（含位置与异常类型），否则线上无从归因
        _ = HostWebView.IsAuthorizedFailClosed(
            () => throw new InvalidOperationException("桥租约失效"), "顶层导航");
        var written = Directory.GetFiles(_logDir);
        Assert.NotEmpty(written);
        var text = string.Concat(written.Select(f => File.ReadAllText(f)));
        Assert.Contains("顶层导航", text);
        Assert.Contains("InvalidOperationException", text);
    }

    [Fact]
    public void HandlersAssignCancelBeforeEvaluatingThePolicy()
    {
        // 文本锚——handler 要 COM 对象跑不了，这里只钉「取消先行」的结构形态；
        // 行为面由上面四条钉住（文本证明不了数学，这一点本仓已被证过多次）。
        var root = FindRepoRoot();
        var top = File.ReadAllText(Path.Combine(
            root, "windows/src/Aegis.Windows.App/WebView/HostWebView.NavigationGuards.cs"));
        var frame = File.ReadAllText(Path.Combine(
            root, "windows/src/Aegis.Windows.App/WebView/HostWebView.cs"));

        foreach (var (label, text) in new[] { ("顶层", top), ("子帧", frame) })
        {
            // xunit 的 string-Contains 没有 userMessage 重载，标签直接进语句里
            // Substring 而非 .. 区间——避免 Range 索引在不同 LangVersion 下的差异
            var handler = text.Substring(
                    text.IndexOf("OnNavigationStarting", StringComparison.Ordinal))
                .Replace("\r\n", "\n");
            Assert.Contains("e.Cancel = true;", handler);
            Assert.DoesNotContain("e.Cancel = !TryAuthorizeNavigation", handler);
        }
    }

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "CLAUDE.md")))
            dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("未找到仓库根（CLAUDE.md）");
    }
}


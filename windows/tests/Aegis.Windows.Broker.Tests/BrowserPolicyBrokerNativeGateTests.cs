using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

/// <summary>C21 批（2026-10-01 审计）：CS-361 门禁探测缓存语义 + CS-372
/// native 必需模式黑名单门禁 + CS-291 KillSwitch 联动组（自
/// BrowserPolicyBrokerTests 拆出——单文件 ≤500 行约束）。
/// CS-346：SecurityLog 统一重定向临时目录（Engage/黑名单拒绝路径会写日志）。</summary>
public sealed class BrowserPolicyBrokerNativeGateTests : IDisposable
{
    public BrowserPolicyBrokerNativeGateTests()
    {
        Directory.CreateDirectory(LogDir);
        SecurityLog.SecurityLogDirOverride = LogDir;
    }

    private string LogDir { get; } =
        Path.Combine(Path.GetTempPath(), $"aegis_broker_gate_log_{Guid.NewGuid():N}");

    public void Dispose()
    {
        SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(LogDir, true); } catch (IOException) { }
    }

    private sealed class StubBlockedHosts(params string[] hosts) : IBlockedHosts
    {
        private readonly HashSet<string> _hosts = new(hosts, StringComparer.OrdinalIgnoreCase);

        public bool IsBlocked(string host) => _hosts.Contains(host);
    }

    // ===== CS-361（2026-10-01 审计）：CS-323 门禁探测缓存语义 =====

    [Fact]
    public void ProbeGate_SuccessResult_IsCachedAcrossDecisions()
    {
        // 成功结果进程内不变——恒缓存（此后每次导航决策不再跑
        // NativeLibrary.TryLoad+GetExport+Free）
        var probes = 0;
        using var broker = new BrowserPolicyBroker(() =>
        {
            probes++;
            return NativePolicyCoreGateResult.Enabled();
        });
        Assert.True(broker.RegisterSession("gate-s", "gate-t"));

        Assert.IsType<Decision.Allow>(broker.EvaluateNavigation(
            "gate-s", "gate-t", 0, "https://example.com/a", "navigation"));
        Assert.IsType<Decision.Allow>(broker.EvaluateNavigation(
            "gate-s", "gate-t", 0, "https://example.com/b", "navigation"));

        Assert.Equal(1, probes);
    }

    [Fact]
    public void ProbeGate_FailureResult_CachedWithinTtl_RetriedAfterTtl()
    {
        // 失败按短 TTL 重试（库文件可能随后就位）——TTL 内缓存，过期后重探
        var probes = 0;
        using var broker = new BrowserPolicyBroker(() =>
        {
            probes++;
            return NativePolicyCoreGateResult.Block("native_policy_core_unavailable");
        });

        Assert.IsType<Decision.Deny>(broker.EvaluateNavigation("s", "t", 0, "https://example.com", "navigation"));
        Assert.IsType<Decision.Deny>(broker.EvaluateNavigation("s", "t", 0, "https://example.com", "navigation"));
        Assert.Equal(1, probes);  // TTL 内失败结果同样缓存（不重探）

        var originalTtl = BrowserPolicyBroker.GateFailureRetryTtl;
        try
        {
            BrowserPolicyBroker.GateFailureRetryTtl = TimeSpan.FromMilliseconds(1);
            System.Threading.Thread.Sleep(50);
            Assert.IsType<Decision.Deny>(broker.EvaluateNavigation("s", "t", 0, "https://example.com", "navigation"));
            Assert.Equal(2, probes);  // TTL 过期——重新探测
        }
        finally
        {
            BrowserPolicyBroker.GateFailureRetryTtl = originalTtl;
        }
    }

    // ===== CS-372（2026-10-01 审计）：native 必需模式黑名单门禁 =====

    [Fact]
    public void EvaluateNavigation_NativeRequired_BlockedHost_DeniesEvenWithoutBridge()
    {
        // 黑名单门禁对 native 必需模式同样强制——桥不可用也先给出
        // threat_blocklist 具体拒绝（此前 null 桥检查在前，该分支不可达）
        using var broker = new BrowserPolicyBroker(
            nativePolicyCoreGate: () => NativePolicyCoreGateResult.Enabled(),
            blockedHosts: new StubBlockedHosts("evil.example"),
            nativePolicyCoreRequiredForTests: true);

        var deny = Assert.IsType<Decision.Deny>(broker.EvaluateNavigation(
            "native-s", "native-t", 0, "https://evil.example/pay", "navigation"));

        Assert.Equal("threat_blocklist", deny.Reason.Code);
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Reason == "threat_blocklist");
    }

    [Fact]
    public void EvaluateNavigation_NativeRequired_UnblockedHostWithoutBridge_DeniesBridgeUnavailable()
    {
        // 非黑名单地址在桥缺失时 fail-closed：native_policy_core_bridge_unavailable
        using var broker = new BrowserPolicyBroker(
            nativePolicyCoreGate: () => NativePolicyCoreGateResult.Enabled(),
            blockedHosts: new StubBlockedHosts("evil.example"),
            nativePolicyCoreRequiredForTests: true);

        var deny = Assert.IsType<Decision.Deny>(broker.EvaluateNavigation(
            "native-s", "native-t", 0, "https://good.example/", "navigation"));

        Assert.Equal("native_policy_core_bridge_unavailable", deny.Reason.Code);
    }

    // ===== CS-291（2026-09-26 审计）：KillSwitch 跨窗口联动 =====

    [Fact]
    public void KillSwitch_SharedInstance_FreezesAllBrokersInjectedWithIt()
    {
        // CS-291（P1）：跨窗口联动——设置窗触发主窗 broker 的开关，无痕窗口
        // broker（注入同一共享实例）的导航/下载/确认链必须同样冻结
        var shared = new KillSwitch();
        var mainBroker = new BrowserPolicyBroker(killSwitch: shared);
        var inPrivateBroker = new BrowserPolicyBroker(killSwitch: shared);
        Assert.True(mainBroker.RegisterSession("main-s", "main-t"));
        Assert.True(inPrivateBroker.RegisterSession("inprivate-s", "inprivate-t"));

        mainBroker.KillSwitch.Engage();  // 仅在主窗 broker 上触发（设置窗路径）

        Assert.True(inPrivateBroker.KillSwitch.IsEngaged);  // 共享实例联动
        Assert.IsType<Decision.Deny>(inPrivateBroker.EvaluateNavigation(
            "inprivate-s", "inprivate-t", 0, "https://example.com", "navigation"));
        Assert.False(inPrivateBroker.AllowDownload(
            "inprivate-s", "inprivate-t", "https://example.com", "x.exe", userConfirmed: true));
        Assert.IsType<Decision.Deny>(inPrivateBroker.RequestNavigationConfirmation(
            "inprivate-s", "inprivate-t", 0, "https://example.com/pay", "navigation"));
    }

    [Fact]
    public void KillSwitch_DefaultBrokersAreIsolated()
    {
        // CS-291 反向锁定：缺省构造（测试语境）各自独立——一个 broker 触发
        // 不影响另一个（生产组合根统一注入 KillSwitch.Shared）
        var first = new BrowserPolicyBroker();
        var second = new BrowserPolicyBroker();
        first.KillSwitch.Engage();
        Assert.False(second.KillSwitch.IsEngaged);
    }

    [Fact]
    public void KillSwitch_Engage_RaisesEngagedEventOnce()
    {
        // CS-367：Engage 首次触发广播 Engaged 通知（主窗常驻横幅的触发源）；
        // 幂等重复 Engage 不重复广播
        var killSwitch = new KillSwitch();
        var fired = 0;
        killSwitch.Engaged += () => fired++;

        killSwitch.Engage();
        killSwitch.Engage();  // 幂等——不再广播

        Assert.Equal(1, fired);
    }
}

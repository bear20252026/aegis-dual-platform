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
        using var broker = new BrowserPolicyBroker(
            () =>
            {
                probes++;
                return NativePolicyCoreGateResult.Enabled();
            },
            nativePolicyCoreRequiredForTests: false);
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
        using var broker = new BrowserPolicyBroker(
            () =>
            {
                probes++;
                return NativePolicyCoreGateResult.Block("native_policy_core_unavailable");
            },
            nativePolicyCoreRequiredForTests: false);

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
        var mainBroker = new BrowserPolicyBroker(
            killSwitch: shared, nativePolicyCoreRequiredForTests: false);
        var inPrivateBroker = new BrowserPolicyBroker(
            killSwitch: shared, nativePolicyCoreRequiredForTests: false);
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
        var first = new BrowserPolicyBroker(nativePolicyCoreRequiredForTests: false);
        var second = new BrowserPolicyBroker(nativePolicyCoreRequiredForTests: false);
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
    /// <summary>审计第七轮（2026-10-04·自 BrowserPolicyBrokerTests 拆入本文件）：
    /// 原生核心的「确认域」端到端语义——高危目标须先批准方可兑换，重放必拒，
    /// 撤销后不得再批。
    ///
    /// 为什么原来它是红的：本用例曾用 https://example.com/… 断言
    /// RequireConfirmation，而 R6-21 把确认域收窄为**仅高危目标**（本机/私网/
    /// 链路本地）后，公网 host 直接 Allow。该测试在 master 上一直失败，只是
    /// `shell: pwsh` 步骤的退出码取自末条原生命令（测试红 + 后续 dotnet publish
    /// 绿 ⇒ 步骤绿），而该 job 又不在必需检查里——红了若干轮无人见
    /// （R7-TOOL-01 的活样本；断言补上后当场暴露）。
    ///
    /// 现按既定口径改用回环地址触发确认域，并补一条**公网不得触发确认**的对照，
    /// 使「只对高危目标确认」这一决策在 C# 侧也有锚点（此前无任何用例）。</summary>
    [Fact]
    public void NativePolicyCoreBridgeRequiresApprovalOnlyForHighRiskTargetsAndThenOnce()
    {
        var libraryPath = Environment.GetEnvironmentVariable("AEGIS_NATIVE_POLICY_CORE_TEST_PATH");
        if (string.IsNullOrWhiteSpace(libraryPath))
        {
            // 与本文件其余原生用例同口径：未声明原生模式时早退（xunit 2.9.3 无
            // Assert.Skip，本仓不为此加包）。"声明了却空转"由 R6-13 的反假绿锚点
            // DeclaredNativeModeMustActuallyRoundTripAndSupportTwoCoexistingBrokers
            // 收口——它在 NativePolicyCoreGate.IsRequired 为真时强制真跑往返。
            return;
        }

        Assert.True(NativePolicyCoreBridge.TryCreate("1.0", libraryPath, out var bridge));
        using var nativeBridge = Assert.IsType<NativePolicyCoreBridge>(bridge);

        const string highRiskUrl = "http://127.0.0.1:8080/confirmation?flow=1";
        const string publicUrl = "https://example.com/confirmation?flow=1";
        Assert.True(nativeBridge.CreateSession("confirmation-session", "confirmation-tab", 0, 120));

        // 对照：公网 host 不进入确认域（R6-21 的收窄口径本身）
        Assert.IsType<Decision.Allow>(nativeBridge.RequestNavigationConfirmation(
            "confirmation-session", "confirmation-tab", 0, publicUrl, "navigation"));

        var pending = Assert.IsType<Decision.RequireConfirmation>(
            nativeBridge.RequestNavigationConfirmation(
                "confirmation-session", "confirmation-tab", 0, highRiskUrl, "navigation"));

        var approved = Assert.IsType<Decision.Allow>(
            nativeBridge.ApproveNavigationConfirmation(pending.Request, highRiskUrl, "navigation"));
        Assert.True(nativeBridge.TryConsumeNavigation(approved.Action, highRiskUrl, "navigation"));
        Assert.False(nativeBridge.TryConsumeNavigation(approved.Action, highRiskUrl, "navigation"));

        var rejected = Assert.IsType<Decision.RequireConfirmation>(
            nativeBridge.RequestNavigationConfirmation(
                "confirmation-session", "confirmation-tab", 0, highRiskUrl, "navigation"));
        Assert.True(nativeBridge.RejectNavigationConfirmation(rejected.Request));
        var afterRejection = Assert.IsType<Decision.Deny>(
            nativeBridge.ApproveNavigationConfirmation(rejected.Request, highRiskUrl, "navigation"));
        Assert.Equal("approval_not_pending", afterRejection.Reason.Code);
    }

    /// <summary>R8-CS-REG-01（第八轮 2026-10-05）：原生模式下**连续两次不同导航**都必须能兑换。
    ///
    /// 回归本体：B4 把 nonce 账本键写成 `"${sessionId}:${action.Nonce}"`（C# 里前导没有
    /// `$` 就不是内插串），于是每条原生导航都往账本记同一个常量——第一次放行，之后恒
    /// `nonce_replay`。装机注册表标记使原生模式正是出货配置，等价于「第一次导航后浏览器锁死」。
    ///
    /// 为什么必需检查里看不见它：本类所有真桥用例都在 `AEGIS_NATIVE_POLICY_CORE_TEST_PATH`
    /// 未设置时早退，而该变量只在 native-policy-artifacts（master push + paths 过滤）与
    /// release-windows（发布）里赋值，两者都不是 PR 的必需检查——PR 上
    /// windows-contract-build 跑 `dotnet test` 时原生分支零行为覆盖（R8-CS-CORE-2 根因）。
    /// 因此同轮另在 `BrokerDenialCodeBehaviorTests` 补了**不依赖原生库**的键格式用例；
    /// 本条的作用是证明调用点确实走那个函数（文本锚证明不了这一点）。</summary>
    [Fact]
    public void NativeMode_TwoDistinctNavigations_BothConsumeWithoutLedgerLockout()
    {
        var libraryPath = Environment.GetEnvironmentVariable("AEGIS_NATIVE_POLICY_CORE_TEST_PATH");
        if (string.IsNullOrWhiteSpace(libraryPath)) return;  // 与本文件其余原生用例同口径

        Assert.True(NativePolicyCoreBridge.TryCreate("1.0", libraryPath, out var created));
        using var bridge = Assert.IsType<NativePolicyCoreBridge>(created);
        using var broker = new BrowserPolicyBroker(
            nativePolicyCoreGate: () => NativePolicyCoreGateResult.Enabled(),
            nativePolicyCoreBridge: bridge,
            nativePolicyCoreRequiredForTests: true);
        Assert.True(broker.RegisterSession("ledger-session", "ledger-tab"));

        // 公网 https + 已注册会话 ⇒ 核心判 allow（native-navigation-decision 向量同口径）
        var first = Assert.IsType<Decision.Allow>(broker.EvaluateNavigation(
            "ledger-session", "ledger-tab", 0, "https://example.com/one", "navigation"));
        Assert.True(broker.TryConsumeNavigation(first.Action, "ledger-session", "ledger-tab",
            0, "https://example.com/one", "navigation"));

        var second = Assert.IsType<Decision.Allow>(broker.EvaluateNavigation(
            "ledger-session", "ledger-tab", 0, "https://example.com/two", "navigation"));
        Assert.True(
            broker.TryConsumeNavigation(second.Action, "ledger-session", "ledger-tab",
                0, "https://example.com/two", "navigation"),
            "第二次不同导航被拒——nonce 账本键退化成常量的可复现证据（R8-CS-REG-01）");
        Assert.DoesNotContain(broker.AuditLog, e => e.Reason == "nonce_replay");

        // 修键不得顺手放开一次性语义：同一授权重放仍必拒
        Assert.False(broker.TryConsumeNavigation(second.Action, "ledger-session", "ledger-tab",
            0, "https://example.com/two", "navigation"));
    }

}

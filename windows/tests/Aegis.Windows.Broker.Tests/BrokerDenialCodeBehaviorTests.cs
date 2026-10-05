using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

/// <summary>第八轮 B4 余量（R8-CS-REG-01 + R8-CS-CORE-1/2，2026-10-05）。
///
/// 为什么单独成文件：这三件事此前在**必需检查**里零行为覆盖——
/// ① R8-CS-REG-01：本轮 B4 把 `"${sessionId}:${action.Nonce}"` 写成了普通字符串
///    （C# 的内插串需要前导 <c>$</c>），于是每次原生导航都往账本记同一个常量：第一次
///    放行、第二次起恒 <c>nonce_replay</c> ⇒ 装机的注册表标记使原生模式正是出货配置，
///    等价于「第一次导航后浏览器锁死」。CI 全绿是因为原生分支的用例都要
///    <c>AEGIS_NATIVE_POLICY_CORE_TEST_PATH</c> 才不早退，而该变量只在
///    native-policy-artifacts（master push + paths）与 release-windows（发布）里赋值，
///    两者都不是 PR 必需检查（R8-CS-CORE-2 的根因）。
/// ② R8-CS-CORE-1：生产拒绝码在测试全树零字符串锚点，现有用例只断
///    <c>is Type&lt;Decision.Deny&gt;</c> ⇒ 改码不红。本类逐条断**行为产生的码**
///    （驱动真实 API 后读 Decision.Reason.Code 与 AuditLog，不是在源码里 grep）。
/// ③ R8-CS-CORE-2：原生必需模式「前置判定」中的**保留地址复判臂**此前零行为断言
///    （黑名单臂与「桥不可得」兜底已由 CS-372 的两条用例钉住，本类不重复）——
///    摘掉那一条 CI 不动，而它是第七轮「本机与内网按裁决放行、元数据段仍拒」这条
///    裁决在原生模式下的唯一兑现点。</summary>
public sealed class BrokerDenialCodeBehaviorTests : IDisposable
{
    // 拒绝路径会写 security.log——重定向到临时目录，绝不落真实用户目录
    //（与 ReservedAddressBoundaryTests 同口径）
    private string LogDir { get; } =
        Path.Combine(Path.GetTempPath(), $"aegis_dccode_{Guid.NewGuid():N}");

    public BrokerDenialCodeBehaviorTests()
    {
        Directory.CreateDirectory(LogDir);
        SecurityLog.SecurityLogDirOverride = LogDir;
    }

    public void Dispose()
    {
        SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(LogDir, true); } catch (IOException) { }
    }

    private static BrowserPolicyBroker Managed() => new(
        nativePolicyCoreGate: () => NativePolicyCoreGateResult.Enabled(),
        nativePolicyCoreRequiredForTests: false);

    /// <summary>原生必需模式 + 无桥（不要求真实原生库）——CS-372 为可测而前置的
    /// 那几条判定分支在这条配置下都可达。</summary>
    private static BrowserPolicyBroker RequiredWithoutBridge() => new(
        nativePolicyCoreGate: () => NativePolicyCoreGateResult.Enabled(),
        nativePolicyCoreBridge: null,
        nativePolicyCoreRequiredForTests: true);

    // ═══ ① 原生 nonce 账本键（R8-CS-REG-01 的直接反证——无原生库也常跑可断）═══

    [Theory]
    [InlineData("session-1", "abc123", "session-1:abc123")]
    [InlineData("s", "", "s:")]
    [InlineData("s1", "n1", "s1:n1")]
    public void NativeNonceLedgerKey_HasExactSessionPrefixedShape(
        string session, string nonce, string expected) =>
        Assert.Equal(expected, BrowserPolicyBroker.NativeNonceLedgerKey(session, nonce));

    [Fact]
    public void NativeNonceLedgerKey_IsPerNavigation_NotASingleConstant()
    {
        // 回归的签名形态：写成 "…${…}" 这类非内插字面量时，四次推导得到同一个字符串，
        // 于是第二次原生导航起 TryRecordConsumedNonce 恒 false（全站锁死）。
        var first = BrowserPolicyBroker.NativeNonceLedgerKey("session-1", "nonce-a");
        var second = BrowserPolicyBroker.NativeNonceLedgerKey("session-1", "nonce-b");
        var otherSession = BrowserPolicyBroker.NativeNonceLedgerKey("session-2", "nonce-a");

        Assert.NotEqual(first, second);
        Assert.NotEqual(first, otherSession);
        Assert.DoesNotContain("$", first);
        Assert.DoesNotContain("{", first);
        Assert.DoesNotContain("}", first);
    }

    [Fact]
    public void NativeNonceLedgerKey_IsEvictableByDestroySession()
    {
        // DestroySession 用 RemoveWhere(nonce => nonce.StartsWith($"{sessionId}:")) 清理。
        // 键不带该前缀时原生条目永不清退 → _consumedNonces 满 MAX 后全站导航永久锁死
        //（审计发现 F 的原始形态）。
        var key = BrowserPolicyBroker.NativeNonceLedgerKey("session-9", "raw-native-nonce");
        // xUnit2009：前缀判定用 Assert.StartsWith，不用 Assert.True(...StartsWith(...))
        Assert.StartsWith("session-9:", key);
    }

    // ═══ ② 拒绝码逐条行为（R8-CS-CORE-1）═══

    [Fact]
    public void EvaluateNavigation_UnknownSession_DeniesWithSessionContext()
    {
        var broker = Managed();   // 不注册会话
        var denied = Assert.IsType<Decision.Deny>(broker.EvaluateNavigation(
            "ghost", "tab-1", 0, "https://example.com/", "navigation"));

        Assert.Equal("session_context", denied.Reason.Code);
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "navigation" && e.Reason == "session_context");
    }

    [Fact]
    public void AllowDownload_UnknownSession_DeniesWithDownloadSessionContext()
    {
        var broker = Managed();
        Assert.False(broker.AllowDownload(
            "ghost", "tab-1", "https://example.com", "x.bin", false));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "download"
            && e.Reason == "download_session_context");
    }

    [Fact]
    public void AllowDownload_WrongTab_DeniesWithDownloadSessionContext()
    {
        // 同一 sessionId、不同 tabId 也是会话上下文不符——不是泛化的“未知会话”
        var broker = Managed();
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        Assert.False(broker.AllowDownload(
            "session-1", "tab-OTHER", "https://example.com", "x.bin", true));
        Assert.Contains(broker.AuditLog, e => e.Reason == "download_session_context");
    }

    [Fact]
    public void RequestNavigationConfirmation_ManagedMode_DeniesWithCoreRequired()
    {
        // 确认状态与授权只存在于原生核心；托管路径不得自行签发（本用例钉该不变量）
        var broker = Managed();
        var denied = Assert.IsType<Decision.Deny>(broker.RequestNavigationConfirmation(
            "session-1", "tab-1", 0, "https://example.com/", "navigation"));

        Assert.Equal("native_confirmation_core_required", denied.Reason.Code);
        Assert.Contains(broker.AuditLog, e => e.Reason == "native_confirmation_core_required");
    }

    [Fact]
    public void ApproveNavigationConfirmation_ManagedMode_DeniesWithCoreRequired()
    {
        var broker = Managed();
        var request = new ApprovalRequest("https://example.com", "GET", "/", "navigation",
            DateTime.UtcNow.AddMinutes(1), "nonce-1");

        var denied = Assert.IsType<Decision.Deny>(broker.ApproveNavigationConfirmation(
            request, "https://example.com/", "navigation"));

        Assert.Equal("native_confirmation_core_required", denied.Reason.Code);
    }

    [Fact]
    public void TryConsumeNavigation_NullAction_DeniesWithAuthorizationMissing()
    {
        var broker = Managed();
        Assert.False(broker.TryConsumeNavigation(null, "session-1", "tab-1", 0,
            "https://example.com/", "navigation"));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Reason == "authorization_missing");
    }

    [Fact]
    public void TryConsumeNavigation_BridgeUnavailableGate_DeniesWithUnavailableCode()
    {
        // 探测结果为「不放行平台 Broker」时，消费点必须响亮留痕而不是静默 false。
        // 口径差异如实钉住：消费点写死 native_policy_core_unavailable，而
        // EvaluateNavigation 走 AllowsNavigationUnderNativePolicyRequirement 时会带出
        // gate 自己的 DenialCode（见下一条对照用例）——同一「桥不可得」事件在两条
        // 出口留下不同码，属登记项（本用例不掩盖它，两处各自钉死）。
        var broker = new BrowserPolicyBroker(
            nativePolicyCoreGate: () => NativePolicyCoreGateResult.Block("native_abi_mismatch"),
            nativePolicyCoreRequiredForTests: false);

        Assert.False(broker.TryConsumeNavigation(null, "session-1", "tab-1", 0,
            "https://example.com/", "navigation"));
        Assert.Contains(broker.AuditLog, e => e.Reason == "native_policy_core_unavailable");
    }

    [Fact]
    public void EvaluateNavigation_BridgeUnavailableGate_ReportsGateDenialCode()
    {
        var broker = new BrowserPolicyBroker(
            nativePolicyCoreGate: () => NativePolicyCoreGateResult.Block("native_abi_mismatch"),
            nativePolicyCoreRequiredForTests: false);

        var denied = Assert.IsType<Decision.Deny>(broker.EvaluateNavigation(
            "session-1", "tab-1", 0, "https://example.com/", "navigation"));

        Assert.Equal("native_abi_mismatch", denied.Reason.Code);
    }

    [Fact]
    public void TryConsumeNavigation_RequiredModeWithoutBridge_DeniesWithDisposed()
    {
        var broker = RequiredWithoutBridge();
        var action = new AuthorizedAction("session-1", "tab-1", 0, "https://example.com",
            "GET", "/", "navigation", DateTime.UtcNow.AddMinutes(1), "nonce-1",
            broker.PolicyVersion);

        Assert.False(broker.TryConsumeNavigation(action, "session-1", "tab-1", 0,
            "https://example.com/", "navigation"));
        Assert.Contains(broker.AuditLog, e => e.Reason == "native_policy_core_disposed");
    }

    // ═══ ③ 原生必需模式的前置判定（R8-CS-CORE-2 的真缺口）═══
    // 同配置下的「黑名单前置」与「桥不可得兜底」已由 BrowserPolicyBrokerNativeGateTests
    // 的 CS-372 两条钉住——本类只补它没覆盖的那一条臂：保留地址复判（第七轮裁决后
    // 与黑名单同段前置），此前零行为断言，摘掉它 CI 不动。

    [Fact]
    public void EvaluateNavigation_RequiredModeWithNullBridge_DeniesReservedAddressFirst()
    {
        var broker = RequiredWithoutBridge();

        var denied = Assert.IsType<Decision.Deny>(broker.EvaluateNavigation(
            "session-1", "tab-1", 0, "http://169.254.169.254/latest/meta-data/", "navigation"));

        // 具体拒绝码，而不是泛化的「桥不可得」
        Assert.Equal("reserved_address", denied.Reason.Code);
        Assert.DoesNotContain(broker.AuditLog,
            e => e.Reason == "native_policy_core_bridge_unavailable");
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Reason == "reserved_address");
    }
}

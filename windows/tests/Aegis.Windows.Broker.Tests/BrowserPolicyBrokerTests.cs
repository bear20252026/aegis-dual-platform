using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

public sealed class BrowserPolicyBrokerTests
{
    [Fact]
    public void AuthorizedNavigationCanBeConsumedOnlyOnce()
    {
        var broker = CreateRegisteredBroker();
        const string url = "https://example.com/path?query=1";
        var action = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation")).Action;

        Assert.True(broker.TryConsumeNavigation(action, "session-1", "tab-1", 0, url, "navigation"));
        Assert.False(broker.TryConsumeNavigation(action, "session-1", "tab-1", 0, url, "navigation"));
    }

    [Fact]
    public void ChangedNavigationParametersInvalidateAuthorization()
    {
        var broker = CreateRegisteredBroker();
        const string authorizedUrl = "https://example.com/path?query=1";
        var action = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, authorizedUrl, "navigation")).Action;

        Assert.False(
            broker.TryConsumeNavigation(
                action,
                "session-1",
                "tab-1",
                0,
                "https://example.com/path?query=2",
                "navigation"));
    }

    [Fact]
    public void UnregisteredOrStaleSessionIsDenied()
    {
        var broker = new BrowserPolicyBroker();

        Assert.IsType<Decision.Deny>(broker.EvaluateNavigation("session-1", "tab-1", 0, "https://example.com", "navigation"));
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        Assert.True(broker.UpdateDocumentGeneration("session-1", "tab-1", 1));
        Assert.IsType<Decision.Deny>(broker.EvaluateNavigation("session-1", "tab-1", 0, "https://example.com", "navigation"));
    }

    [Fact]
    public void DocumentGenerationAdvancesOnlyOneStepForTheRegisteredTab()
    {
        var broker = CreateRegisteredBroker();

        Assert.False(broker.UpdateDocumentGeneration("session-1", "other-tab", 1));
        Assert.False(broker.UpdateDocumentGeneration("session-1", "tab-1", 2));
        Assert.False(broker.UpdateDocumentGeneration("session-1", "tab-1", 0));
        Assert.True(broker.UpdateDocumentGeneration("session-1", "tab-1", 1));
    }

    [Fact]
    public void RequiredNativePolicyCoreFailureClosesNavigationAndConsumption()
    {
        var broker = new BrowserPolicyBroker(
            () => NativePolicyCoreGateResult.Block("native_policy_core_unavailable"));
        Assert.True(broker.RegisterSession("session-1", "tab-1"));

        var denied = Assert.IsType<Decision.Deny>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, "https://example.com", "navigation"));

        Assert.Equal("native_policy_core_unavailable", denied.Reason.Code);
        Assert.False(broker.TryConsumeNavigation(null, "session-1", "tab-1", 0, "https://example.com", "navigation"));
    }

    [Fact]
    public void DownloadAttemptsAreDeniedAndAudited()
    {
        // 审计 C1（全面审计 2026-09-04）：下载没有契约授权动作——
        // DenyDownload 必须 fail-closed 留痕，供 HostWebView 调用。
        var broker = CreateRegisteredBroker();

        broker.DenyDownload("session-1", "tab-1", "https://example.com/file.zip");

        var entry = Assert.Single(broker.AuditLog, e => e.Scope == "download");
        Assert.Equal("deny", entry.Decision);
        Assert.Equal("https://example.com/file.zip", entry.Origin);
        Assert.Equal("download_not_authorized", entry.Reason);
    }

    [Fact]
    public void BuiltNativePolicyCoreDllHasExpectedAbiWhenProvided()
    {
        var libraryPath = Environment.GetEnvironmentVariable("AEGIS_NATIVE_POLICY_CORE_TEST_PATH");
        if (string.IsNullOrWhiteSpace(libraryPath))
            return;

        var result = NativePolicyCoreGate.ProbeLibrary(libraryPath);

        Assert.True(result.AllowsPlatformBroker);
        Assert.Null(result.DenialCode);
    }

    // ===== CS-073（审计 2026-09-25）：TryCreate(null) 空参拒绝 =====

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void NativePolicyCoreBridgeTryCreateRejectsInvalidPolicyVersion(string? policyVersion)
    {
        // policyVersion 缺失（版本号是 ABI 契约的一部分）→ fail-closed false，
        // 且 out bridge 保持 null（不产生半初始化桥对象）
        Assert.False(NativePolicyCoreBridge.TryCreate(policyVersion!, null, out var bridge));
        Assert.Null(bridge);
    }

    [Fact]
    public void NativePolicyCoreBridgeMapsDecisionAndRejectsReplayWhenEnabled()
    {
        var libraryPath = Environment.GetEnvironmentVariable("AEGIS_NATIVE_POLICY_CORE_TEST_PATH");
        if (string.IsNullOrWhiteSpace(libraryPath))
            return;

        Assert.True(NativePolicyCoreBridge.TryCreate("1.0", libraryPath, out var bridge));
        using (var nativeBridge = Assert.IsType<NativePolicyCoreBridge>(bridge))
        {
            Assert.True(nativeBridge.CreateSession("native-session", "native-tab", 0, 120));
            var allow = Assert.IsType<Decision.Allow>(
                nativeBridge.EvaluateNavigation("native-session", "native-tab", 0,
                    "HTTPS://Example.COM:443/path?x=1#ignored", "navigation"));

            Assert.Equal("https://example.com", allow.Action.Origin);
            Assert.Equal("/path?x=1", allow.Action.CanonicalParameters);
            Assert.True(nativeBridge.TryConsumeNavigation(
                allow.Action, "https://example.com/path?x=1#executed", "navigation"));
            Assert.False(nativeBridge.TryConsumeNavigation(
                allow.Action, "https://example.com/path?x=1", "navigation"));
        }
    }

    [Fact]
    public void NativePolicyCoreBridgeMapsCompleteConfirmationRequest()
    {
        var decision = NativePolicyCoreBridge.ParseDecisionPayload("""
            {"abi_version":3,"decision":"require_confirmation","request":{
              "origin":"https://payments.example","method":"POST","path":"/transfers",
              "scope":"payment:create","expires_at":1700000000,"nonce":"approval-nonce"}}
            """);

        var confirmation = Assert.IsType<Decision.RequireConfirmation>(decision);
        Assert.Equal("https://payments.example", confirmation.Request.Origin);
        Assert.Equal("POST", confirmation.Request.Method);
        Assert.Equal("/transfers", confirmation.Request.Path);
        Assert.Equal("payment:create", confirmation.Request.Scope);
        Assert.Equal(DateTimeOffset.FromUnixTimeSeconds(1_700_000_000).UtcDateTime, confirmation.Request.ExpiresAt);
        Assert.Equal("approval-nonce", confirmation.Request.Nonce);
    }

    [Fact]
    public void NativePolicyCoreBridgeRequiresApprovalBeforeConfirmationNavigationCanConsume()
    {
        var libraryPath = Environment.GetEnvironmentVariable("AEGIS_NATIVE_POLICY_CORE_TEST_PATH");
        if (string.IsNullOrWhiteSpace(libraryPath))
            return;

        Assert.True(NativePolicyCoreBridge.TryCreate("1.0", libraryPath, out var bridge));
        using (var nativeBridge = Assert.IsType<NativePolicyCoreBridge>(bridge))
        {
            const string url = "https://example.com/confirmation?flow=1";
            Assert.True(nativeBridge.CreateSession("confirmation-session", "confirmation-tab", 0, 120));
            var pending = Assert.IsType<Decision.RequireConfirmation>(
                nativeBridge.RequestNavigationConfirmation(
                    "confirmation-session", "confirmation-tab", 0, url, "navigation"));

            var approved = Assert.IsType<Decision.Allow>(
                nativeBridge.ApproveNavigationConfirmation(pending.Request, url, "navigation"));
            Assert.True(nativeBridge.TryConsumeNavigation(approved.Action, url, "navigation"));
            Assert.False(nativeBridge.TryConsumeNavigation(approved.Action, url, "navigation"));

            var rejected = Assert.IsType<Decision.RequireConfirmation>(
                nativeBridge.RequestNavigationConfirmation(
                    "confirmation-session", "confirmation-tab", 0, url, "navigation"));
            Assert.True(nativeBridge.RejectNavigationConfirmation(rejected.Request));
            var afterRejection = Assert.IsType<Decision.Deny>(
                nativeBridge.ApproveNavigationConfirmation(rejected.Request, url, "navigation"));
            Assert.Equal("approval_not_pending", afterRejection.Reason.Code);
        }
    }

    [Fact]
    public void NativePolicyCoreBridgeRejectsPreviousAbiResponse()
    {
        var exception = Assert.Throws<InvalidOperationException>(() =>
            NativePolicyCoreBridge.ParseDecisionPayload("""
                {"abi_version":1,"decision":"deny","reason":{
                  "code":"legacy","detail":"legacy ABI","explanation":"denied"}}
                """));

        Assert.Contains("ABI", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void BrowserPolicyBrokerUsesNativeDecisionWhenNativeModeIsEnabled()
    {
        var libraryPath = Environment.GetEnvironmentVariable(NativePolicyCoreGate.LibraryPathEnvironmentVariable);
        if (!string.Equals(Environment.GetEnvironmentVariable(NativePolicyCoreGate.EnableEnvironmentVariable), "1", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(libraryPath))
            return;

        using var broker = new BrowserPolicyBroker();
        Assert.True(broker.RegisterSession("native-broker-session", "native-broker-tab"));
        var allow = Assert.IsType<Decision.Allow>(broker.EvaluateNavigation(
            "native-broker-session", "native-broker-tab", 0,
            "https://example.com/native?ready=1", "navigation"));
        Assert.True(broker.TryConsumeNavigation(
            allow.Action, "native-broker-session", "native-broker-tab", 0,
            "https://example.com/native?ready=1#fragment", "navigation"));
        Assert.False(broker.TryConsumeNavigation(
            allow.Action, "native-broker-session", "native-broker-tab", 0,
            "https://example.com/native?ready=1", "navigation"));
    }

    [Fact]
    public void DestroyedSessionCannotCreateNewAuthorizations()
    {
        var broker = CreateRegisteredBroker();
        broker.DestroySession("session-1");

        Assert.IsType<Decision.Deny>(broker.EvaluateNavigation("session-1", "tab-1", 0, "https://example.com", "navigation"));
    }

    [Fact]
    public void DestroyedSessionCannotConsumeAnAlreadyIssuedAuthorization()
    {
        var broker = CreateRegisteredBroker();
        const string url = "https://example.com";
        var action = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation")).Action;
        broker.DestroySession("session-1");

        Assert.False(broker.TryConsumeNavigation(action, "session-1", "tab-1", 0, url, "navigation"));
    }

    [Theory]
    [InlineData("HTTPS://Example.Org:443/a?b=1#ignored", "https://example.org", "/a?b=1")]
    [InlineData("http://example.org:8080?x=1", "http://example.org:8080", "/?x=1")]
    public void NavigationAuthorizationCanonicalizesOriginAndPathQuery(
        string rawUrl,
        string expectedOrigin,
        string expectedParameters)
    {
        var broker = CreateRegisteredBroker();
        var action = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, rawUrl, "navigation")).Action;

        Assert.Equal(expectedOrigin, action.Origin);
        Assert.Equal(expectedParameters, action.CanonicalParameters);
    }

    private static BrowserPolicyBroker CreateRegisteredBroker()
    {
        var broker = new BrowserPolicyBroker();
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        return broker;
    }

    // ===== CS-008..017（审计 2026-09-25）：KillSwitch 门禁 + Register/Consume/黑名单边界 =====

    [Fact]
    public void AllowDownload_KillSwitch_DeniesAndAudits()
    {
        // CS-008：紧急终止期间下载必须拒绝，且审计含 kill_switch_engaged
        var broker = CreateRegisteredBroker();
        broker.KillSwitch.Engage();

        Assert.False(broker.AllowDownload("session-1", "tab-1", "https://example.com", "file.zip", userConfirmed: true));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "download" && e.Reason == "kill_switch_engaged");
    }

    [Fact]
    public void EvaluateNavigation_KillSwitch_Denies()
    {
        // CS-009：紧急终止期间全部导航冻结（含已注册会话）
        var broker = CreateRegisteredBroker();
        broker.KillSwitch.Engage();

        var decision = broker.EvaluateNavigation("session-1", "tab-1", 0, "https://example.com", "navigation");
        var deny = Assert.IsType<Decision.Deny>(decision);
        Assert.Equal("kill_switch_engaged", deny.Reason.Code);
    }

    [Fact]
    public void RequestNavigationConfirmation_KillSwitch_Denies()
    {
        // CS-007 回归：确认请求入口同样接 KillSwitch（此前唯一未接的入口）
        var broker = CreateRegisteredBroker();
        broker.KillSwitch.Engage();

        var decision = broker.RequestNavigationConfirmation(
            "session-1", "tab-1", 0, "https://example.com/pay", "navigation");
        var deny = Assert.IsType<Decision.Deny>(decision);
        Assert.Equal("kill_switch_engaged", deny.Reason.Code);
    }

    [Fact]
    public void RegisterSession_DuplicateSessionId_ReturnsFalse()
    {
        // CS-010：重复 sessionId 拒绝（会话池幂等保护）
        var broker = new BrowserPolicyBroker();
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        Assert.False(broker.RegisterSession("session-1", "tab-2"));
    }

    [Fact]
    public void RegisterSession_AbovePoolCap_ReturnsFalse()
    {
        // CS-011：会话池 1024 上限（与 Rust MAX_SESSIONS 对等）——超限 fail-closed
        var broker = new BrowserPolicyBroker();
        for (var i = 0; i < 1024; i++)
            Assert.True(broker.RegisterSession($"session-{i}", $"tab-{i}"));
        Assert.False(broker.RegisterSession("session-overflow", "tab-overflow"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void RegisterSession_NullOrBlank_ReturnsFalse(string? sessionId)
    {
        // CS-012：null/空白 sessionId 拒绝
        var broker = new BrowserPolicyBroker();
        Assert.False(broker.RegisterSession(sessionId!, "tab-1"));
    }

    [Fact]
    public void UpdateDocumentGeneration_RejectsJumpBackwardAndWrongTab()
    {
        // CS-013：严格单步推进——拒绝跳跃（+2）、回退、错标签
        var broker = CreateRegisteredBroker();

        Assert.False(broker.UpdateDocumentGeneration("session-1", "tab-1", 2), "跳跃 +2 拒绝");
        Assert.False(broker.UpdateDocumentGeneration("session-1", "tab-1", 0), "回退拒绝");
        Assert.False(broker.UpdateDocumentGeneration("session-1", "other-tab", 1), "错标签拒绝");
        Assert.True(broker.UpdateDocumentGeneration("session-1", "tab-1", 1), "严格 +1 放行");
    }

    [Fact]
    public void IsValid_ExpiredAuthorization_ReturnsFalse()
    {
        // CS-014：过期授权 fail-closed
        var broker = CreateRegisteredBroker();
        const string url = "https://example.com";
        var action = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation")).Action;

        Assert.True(broker.IsValid(action, 0));
        var expired = action with { ExpiresAt = DateTime.UtcNow.AddMinutes(-1) };
        Assert.False(broker.IsValid(expired, 0));
    }

    [Fact]
    public void TryConsumeNavigation_SameNonceReplay_Denied()
    {
        // CS-015：同 nonce 二次消费拒绝（一次性语义——即使授权其余字段合法）
        var broker = CreateRegisteredBroker();
        const string url = "https://example.com/path";
        var first = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation")).Action;

        Assert.True(broker.TryConsumeNavigation(first, "session-1", "tab-1", 0, url, "navigation"));

        // 重放：同 nonce 换全新 action 实例（模拟攻击者复用截获的 nonce）
        var replay = first with { Nonce = first.Nonce };
        Assert.False(broker.TryConsumeNavigation(replay, "session-1", "tab-1", 0, url, "navigation"));
    }

    private sealed class StubBlockedHosts(params string[] hosts) : IBlockedHosts
    {
        private readonly HashSet<string> _hosts = new(hosts, StringComparer.OrdinalIgnoreCase);

        public bool IsBlocked(string host) => _hosts.Contains(host);
    }

    [Fact]
    public void IsHostBlocked_DelegatesToInjectedSnapshot()
    {
        // CS-016：注入 blockedHosts 快照——子资源层查询必须走注入实例
        var broker = new BrowserPolicyBroker(blockedHosts: new StubBlockedHosts("evil.example"));

        Assert.True(broker.IsHostBlocked("evil.example"));
        Assert.False(broker.IsHostBlocked("good.example"));
    }

    [Fact]
    public void UpdateBlockedHosts_NullFallsBackToAllowAll()
    {
        // CS-017：UpdateBlockedHosts(null) 回退 NoBlockedHosts——导航不再被拦
        var broker = new BrowserPolicyBroker(blockedHosts: new StubBlockedHosts("evil.example"));
        broker.UpdateBlockedHosts(null);

        Assert.False(broker.IsHostBlocked("evil.example"));
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, "https://evil.example", "navigation"));
    }
}

using Aegis.Windows.Broker;
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
    public void BuiltNativePolicyCoreDllHasExpectedAbiWhenProvided()
    {
        var libraryPath = Environment.GetEnvironmentVariable("AEGIS_NATIVE_POLICY_CORE_TEST_PATH");
        if (string.IsNullOrWhiteSpace(libraryPath))
            return;

        var result = NativePolicyCoreGate.ProbeLibrary(libraryPath);

        Assert.True(result.AllowsPlatformBroker);
        Assert.Null(result.DenialCode);
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
}

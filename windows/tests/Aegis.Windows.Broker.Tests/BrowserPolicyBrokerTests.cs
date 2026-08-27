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

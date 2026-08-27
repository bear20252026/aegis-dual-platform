using Aegis.Windows.Broker;

namespace Aegis.Windows.Broker.Tests;

public sealed class BrowserPolicyBrokerTests
{
    [Fact]
    public void AuthorizedNavigationCanBeConsumedOnlyOnce()
    {
        var broker = new BrowserPolicyBroker();
        const string url = "https://example.com/path?query=1";
        var action = Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation")).Action;

        Assert.True(broker.TryConsumeNavigation(action, "session-1", "tab-1", 0, url, "navigation"));
        Assert.False(broker.TryConsumeNavigation(action, "session-1", "tab-1", 0, url, "navigation"));
    }

    [Fact]
    public void ChangedNavigationParametersInvalidateAuthorization()
    {
        var broker = new BrowserPolicyBroker();
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
}

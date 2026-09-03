namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>M1-T2（ADR-009）：broker 威胁黑名单导航门禁单测——
/// 命中 fail-closed 留痕（threat_blocklist），黑名单更新原子换引用。</summary>
public sealed class BrokerThreatGateTests
{
    [Fact]
    public void BlacklistedHostNavigationIsDeniedAndAudited()
    {
        var broker = new BrowserPolicyBroker(
            blockedHosts: new BlockedHosts(["evil.example"]));
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        Assert.True(broker.UpdateDocumentGeneration("session-1", "tab-1", 1));

        var decision = broker.EvaluateNavigation(
            "session-1", "tab-1", 1, "https://evil.example/page", "navigation");

        var deny = Assert.IsType<Decision.Deny>(decision);
        Assert.Equal("threat_blocklist", deny.Reason.Code);
        // 子域同样命中
        var subDecision = broker.EvaluateNavigation(
            "session-1", "tab-1", 1, "https://cdn.evil.example/x", "navigation");
        Assert.IsType<Decision.Deny>(subDecision);
        // 审计留痕
        Assert.Contains(broker.AuditLog, e => e.Reason == "threat_blocklist");
    }

    [Fact]
    public void NonBlacklistedHostStillAllowed()
    {
        var broker = new BrowserPolicyBroker(
            blockedHosts: new BlockedHosts(["evil.example"]));
        Assert.True(broker.RegisterSession("session-1", "tab-1"));

        var decision = broker.EvaluateNavigation(
            "session-1", "tab-1", 0, "https://example.org", "navigation");

        Assert.IsType<Decision.Allow>(decision);
    }

    [Fact]
    public void UpdateBlockedHostsSwapsSnapshotAtomically()
    {
        var broker = new BrowserPolicyBroker();
        Assert.True(broker.RegisterSession("session-1", "tab-1"));

        broker.UpdateBlockedHosts(new BlockedHosts(["newly.evil.example"]));
        Assert.True(broker.IsHostBlocked("newly.evil.example"));

        broker.UpdateBlockedHosts(NoBlockedHosts.Instance);
        Assert.False(broker.IsHostBlocked("newly.evil.example"));
    }
}

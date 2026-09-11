namespace Aegis.Windows.Core.Tests;

using System;
using System.Threading;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Privacy;
using Aegis.Windows.Core.Tabs;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>架构解耦（第 1/2/4 项）回归：验证 HostWebView 只依赖 IBroker 接口
///（可用假实现）、隐私决策走注入的 IPrivacySettings（不直接读静态）、
/// NtpBridgeFactory.CreatePrivate 返回空数据无痕桥。证明这些接缝真正可注入/可测。</summary>
public sealed class DecouplingTests
{
    /// <summary>最小假 Broker：全部方法 fail-closed 默认（0/false）。证明
    /// HostWebView 不依赖具体 BrowserPolicyBroker 即可构造。</summary>
    private sealed class FakeBroker : IBroker
    {
        public bool RegisterSession(string sessionId, string tabId, ulong generation = 0) => true;
        public void DestroySession(string sessionId) { }
        public bool UpdateDocumentGeneration(string sessionId, string tabId, ulong generation) => true;
        public Decision EvaluateNavigation(string s, string t, ulong g, string u, string scope) =>
            new Decision.Deny(new DenyReason("fake", "fake"));
        public Decision RequestNavigationConfirmation(string s, string t, ulong g, string u, string scope) =>
            new Decision.Deny(new DenyReason("fake", "fake"));
        public Decision ApproveNavigationConfirmation(ApprovalRequest r, string u, string scope) =>
            new Decision.Deny(new DenyReason("fake", "fake"));
        public bool RejectNavigationConfirmation(ApprovalRequest request) => true;
        public bool TryConsumeNavigation(AuthorizedAction? a, string s, string t, ulong g, string u, string scope) => true;
        public bool AllowDownload(string s, string t, string o, string f, bool c) => true;
        public void DenyDownload(string s, string t, string o) { }
        public bool IsHostBlocked(string host) => false;
        public void Dispose() { }
    }

    private sealed class FakePrivacy : IPrivacySettings
    {
        public FakePrivacy(bool httpsOnly, int level) { HttpsOnly = httpsOnly; ProtectionLevel = level; }
        public bool HttpsOnly { get; }
        public int ProtectionLevel { get; }
    }

    [Fact]
    public void HostWebView_AcceptsFakeBrokerAndInjectedPrivacy()
    {
        // 无需真实 WebView 核心——只验证构造接缝成立（第 4/2 项：依赖接口而非具体类）
        var host = new HostWebView(new FakeBroker(), "s", "t", new FakePrivacy(httpsOnly: false, level: 0));
        Assert.NotNull(host);
    }

    [Fact]
    public void LivePrivacySettings_ReadsStaticCurrentValue()
    {
        // 注入默认实现与静态单一事实源一致（第 2 项：HostWebView 读接口，接口透传静态）
        var before = PrivacySettings.HttpsOnly;
        PrivacySettings.HttpsOnly = !before;
        try
        {
            Assert.Equal(!before, LivePrivacySettings.Instance.HttpsOnly);
        }
        finally
        {
            PrivacySettings.HttpsOnly = before;
        }
    }

    private static void RunSta(Action action)
    {
        Exception? caught = null;
        var thread = new Thread(() =>
        {
            try { action(); }
            catch (Exception ex) { caught = ex; }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        Assert.Null(caught);
    }

    [Fact]
    public void CreatePrivate_BridgeReturnsEmptyDataAndEchoesEngine()
    {
        RunSta(() =>
        {
            var runtime = new TabRuntime(new FakeBroker(), new Tab(Guid.NewGuid().ToString("N"), NtpAssets.Url));
            var bridge = NtpBridgeFactory.CreatePrivate(runtime, "baidu");
            var noArgs = System.Text.Json.JsonSerializer.SerializeToElement(Array.Empty<string>());
            // 数据面全部为空/零（无痕不读真实用户数据——第 3 项语义）
            Assert.Equal("[]", System.Text.Json.JsonSerializer.Serialize(bridge.Dispatch("bookmarks", noArgs)));
            Assert.Equal(0, bridge.Dispatch("hasSaved", noArgs));
            Assert.Equal("[]", System.Text.Json.JsonSerializer.Serialize(bridge.Dispatch("importScan", noArgs)));
            // 引擎回显注入值（setEngine 不回写——无痕窗口语义）
            var engineJson = System.Text.Json.JsonSerializer.Serialize(bridge.Dispatch("getEngine", noArgs));
            Assert.Contains("\"engine\":\"baidu\"", engineJson);
            // 导入能力空结果
            var importArgs = System.Text.Json.JsonSerializer.SerializeToElement(new[] { "all" });
            var importJson = System.Text.Json.JsonSerializer.Serialize(bridge.Dispatch("importBookmarks", importArgs));
            Assert.Contains("\"imported\":0", importJson);
        });
    }
}

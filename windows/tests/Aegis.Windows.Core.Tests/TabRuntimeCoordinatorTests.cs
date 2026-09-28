namespace Aegis.Windows.Core.Tests;

using System;
using System.Threading;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>C19b 批（审计 2026-09-26）：CS-330 TabRuntimeCoordinator 校验/重试
/// 分支直测——ValidateNavigationTarget 探针异常拒绝、重试耗尽触发
/// NtpNavigationFailed（此前零覆盖）。WPF 控件构造需 STA。</summary>
public sealed class TabRuntimeCoordinatorTests
{
    private sealed class FakeBroker : Aegis.Windows.Broker.IBroker
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
    public void ValidateNavigationTarget_ThrowingProbe_IsRejected()
    {
        // CS-330：窗口存活探针自身抛异常（窗口已进入关闭序列）——安全拒绝
        RunSta(() =>
        {
            var runtimes = new Dictionary<string, TabRuntime>();
            using var coordinator = new TabRuntimeCoordinator(runtimes, new System.Windows.Controls.Grid());
            var runtime = new TabRuntime(new FakeBroker(), new Tab(Guid.NewGuid().ToString("N"), "https://ntp.aegis.local/"));
            using var lifetime = new TabRuntimeLifetime(runtime);

            Assert.False(coordinator.ValidateNavigationTarget(
                "tab-1", runtime, lifetime, () => throw new InvalidOperationException("closing")));
        });
    }

    [Fact]
    public void ValidateNavigationTarget_FalseProbe_IsRejected()
    {
        // CS-330：探针返回 false（窗口已关闭）——拒绝
        RunSta(() =>
        {
            var runtimes = new Dictionary<string, TabRuntime>();
            using var coordinator = new TabRuntimeCoordinator(runtimes, new System.Windows.Controls.Grid());
            var runtime = new TabRuntime(new FakeBroker(), new Tab(Guid.NewGuid().ToString("N"), "https://ntp.aegis.local/"));
            using var lifetime = new TabRuntimeLifetime(runtime);

            Assert.False(coordinator.ValidateNavigationTarget(
                "tab-1", runtime, lifetime, () => false));
        });
    }

    [Fact]
    public void ValidateNavigationTarget_StaleRuntimeReference_IsRejected()
    {
        // CS-330：快照引用已被替换（同 id 重建）——拒绝
        RunSta(() =>
        {
            var runtimes = new Dictionary<string, TabRuntime>();
            using var coordinator = new TabRuntimeCoordinator(runtimes, new System.Windows.Controls.Grid());
            using var stale = new TabRuntime(new FakeBroker(), new Tab(Guid.NewGuid().ToString("N"), "https://a.example"));
            using var fresh = new TabRuntime(new FakeBroker(), new Tab(Guid.NewGuid().ToString("N"), "https://a.example"));
            runtimes["tab-1"] = fresh;  // 当前对象已不是快照里的 stale

            Assert.False(coordinator.ValidateNavigationTarget(
                "tab-1", stale, new TabRuntimeLifetime(stale), () => true));
        });
    }

    [Fact]
    public void OnVirtualHostRetryExhausted_FiresNtpNavigationFailed()
    {
        // CS-330：重试耗尽 → NtpNavigationFailed（主窗口停加载条/展示错误的
        // 触发源）——事件参数 (tabId, status) 原样传递
        RunSta(() =>
        {
            var runtimes = new Dictionary<string, TabRuntime>();
            using var coordinator = new TabRuntimeCoordinator(runtimes, new System.Windows.Controls.Grid());
            var fired = new List<(string TabId, Microsoft.Web.WebView2.Core.CoreWebView2WebErrorStatus Status)>();
            coordinator.NtpNavigationFailed += (tabId, status) => fired.Add((tabId, status));

            coordinator.OnVirtualHostRetryExhausted(
                "tab-1", Microsoft.Web.WebView2.Core.CoreWebView2WebErrorStatus.ConnectionAborted);

            var evt = Assert.Single(fired);
            Assert.Equal("tab-1", evt.TabId);
            Assert.Equal(Microsoft.Web.WebView2.Core.CoreWebView2WebErrorStatus.ConnectionAborted, evt.Status);
        });
    }
}

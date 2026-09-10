namespace Aegis.Windows.Core.Tests;

using System;
using System.Threading;
using System.Windows.Controls;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>MainWindow 拆分第三批（确认面板/标签拖拽）控制器冒烟：真实 WPF
/// 控件在 STA 线程构造与驱动，覆盖登记→覆盖→失效允许→拒绝的状态迁移。</summary>
public sealed class ApprovalPanelControllerTests
{
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
    public void RequestShowsPanelAndSecondRequestReplacesPending()
    {
        RunSta(() =>
        {
            var overlay = new StackPanel();
            var (origin, path, scope, expiry) = (new TextBlock(), new TextBlock(), new TextBlock(), new TextBlock());
            var deny = new Button();
            var enabled = true;
            var rejections = new System.Collections.Generic.List<string>();
            var controller = new ApprovalPanelController(
                overlay, origin, path, scope, expiry, deny,
                v => enabled = v,
                _ => null,  // 无可解析 runtime（标签已销毁场景）
                rejections.Add);

            var request = new Aegis.Windows.WebView.NavigationConfirmationRequestedEventArgs(
                new ApprovalRequest(
                    Origin: "https://example.com",
                    Method: "GET",
                    Path: "/submit",
                    Scope: "navigation",
                    ExpiresAt: DateTime.UtcNow.AddMinutes(2),
                    Nonce: "n-1"));

            controller.Request("tab-a", request);
            Assert.True(controller.IsVisible);
            Assert.Equal("tab-a", controller.PendingTabId);
            Assert.Equal("https://example.com", origin.Text);
            Assert.False(enabled);  // 导航控件被禁用

            // 第二个不同标签的请求覆盖 pending（前一 runtime 不可解析则跳过拒绝）
            controller.Request("tab-b", request);
            Assert.Equal("tab-b", controller.PendingTabId);

            // 宿主侧解决 → 仅撤面板
            controller.Resolved();
            Assert.False(controller.IsVisible);
            Assert.Null(controller.PendingTabId);
            Assert.True(enabled);
            Assert.Empty(rejections);
        });
    }

    [Fact]
    public void AllowWithUnresolvablePendingHidesAndReportsStale()
    {
        RunSta(() =>
        {
            var overlay = new StackPanel();
            var deny = new Button();
            var rejections = new System.Collections.Generic.List<string>();
            var controller = new ApprovalPanelController(
                overlay, new TextBlock(), new TextBlock(), new TextBlock(), new TextBlock(), deny,
                _ => { }, _ => null, rejections.Add);
            var request = new Aegis.Windows.WebView.NavigationConfirmationRequestedEventArgs(
                new ApprovalRequest(
                    "https://example.com", "GET", "/x", "navigation",
                    DateTime.UtcNow.AddMinutes(2), "n-2"));
            controller.Request("tab-a", request);

            // pending 标签已销毁（resolveRuntime=null）→ 撤面板 + 失效告知
            controller.Allow();
            Assert.False(controller.IsVisible);
            Assert.Null(controller.PendingTabId);
            var message = Assert.Single(rejections);
            Assert.Contains("失效", message);
        });
    }

    [Fact]
    public void DenyWithoutRuntimeStillReportsDenial()
    {
        RunSta(() =>
        {
            var overlay = new StackPanel();
            var deny = new Button();
            var rejections = new System.Collections.Generic.List<string>();
            var controller = new ApprovalPanelController(
                overlay, new TextBlock(), new TextBlock(), new TextBlock(), new TextBlock(), deny,
                _ => { }, _ => null, rejections.Add);
            controller.Deny();
            Assert.Equal("已拒绝该导航请求。", Assert.Single(rejections));
        });
    }

    [Fact]
    public void TabStripDragControllerConstructs()
    {
        RunSta(() =>
        {
            var strip = new ListBox();
            var tabs = new TabManager();
            _ = new TabStripDragController(strip, tabs);
            // DragOver 无命中容器/无数据 → None 且 Handled（安全路径不抛）
            // （无法在无渲染窗口下做真实命中测试——构造即用例）
        });
    }
}

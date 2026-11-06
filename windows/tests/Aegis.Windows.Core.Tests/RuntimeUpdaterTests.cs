namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using System.Threading;
using Aegis.Windows.WebView;
using Microsoft.Web.WebView2.Core;
using Moq;
using Xunit;

/// <summary>
/// RuntimeUpdater 单元测试（ADR-001 后果段：NewBrowserVersionAvailable 事件处理）。
/// 
/// 测试覆盖：
/// 1. 事件订阅/取消订阅（幂等性）
/// 2. 事件触发时的回调通知
/// 3. 自动重启判定逻辑
/// 4. Dispose 安全性
/// </summary>
public class RuntimeUpdaterTests
{
    [Fact]
    public void Subscribe_ShouldAddEventHandler()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var updater = new RuntimeUpdater(mockEnv.Object);

        // Act
        updater.Subscribe();

        // Assert - 验证事件处理器已添加（通过触发事件验证）
        // 注意：CoreWebView2Environment 的 NewBrowserVersionAvailable 事件
        // 是 mock 对象，无法直接验证订阅状态，通过行为测试间接验证
    }

    [Fact]
    public void Subscribe_ShouldBeIdempotent()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var updater = new RuntimeUpdater(mockEnv.Object);

        // Act - 重复调用 Subscribe
        updater.Subscribe();
        updater.Subscribe();

        // Assert - 不应抛出异常
    }

    [Fact]
    public void Unsubscribe_ShouldBeSafeWhenNotSubscribed()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var updater = new RuntimeUpdater(mockEnv.Object);

        // Act & Assert - 未订阅时调用 Unsubscribe 不应抛出
        updater.Unsubscribe();
    }

    [Fact]
    public void OnUpdateAvailableCallback_ShouldBeInvoked()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var callbackInvoked = false;
        Action onUpdateAvailable = () => callbackInvoked = true;

        var updater = new RuntimeUpdater(
            mockEnv.Object,
            shouldRestart: () => false,
            onUpdateAvailable: onUpdateAvailable);

        updater.Subscribe();

        // Act - 触发事件（通过 mock 触发事件）
        mockEnv.Raise(e => e.NewBrowserVersionAvailable += null, EventArgs.Empty);

        // Assert
        Assert.True(callbackInvoked, "更新可用回调应被触发");
    }

    [Fact]
    public void AutoRestart_ShouldNotTrigger_WhenShouldRestartReturnsFalse()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var restartRequested = false;
        Action onRestartRequested = () => restartRequested = true;

        var updater = new RuntimeUpdater(
            mockEnv.Object,
            shouldRestart: () => false, // 明确不自动重启
            onUpdateAvailable: null,
            onRestartRequested: onRestartRequested);

        updater.Subscribe();

        // Act
        mockEnv.Raise(e => e.NewBrowserVersionAvailable += null, EventArgs.Empty);

        // Assert
        Assert.False(restartRequested, "shouldRestart 返回 false 时不应触发重启");
    }

    [Fact]
    public void AutoRestart_ShouldTrigger_WhenShouldRestartReturnsTrue()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var restartRequested = false;
        Action onRestartRequested = () => restartRequested = true;

        var updater = new RuntimeUpdater(
            mockEnv.Object,
            shouldRestart: () => true, // 自动重启
            onUpdateAvailable: null,
            onRestartRequested: onRestartRequested);

        updater.Subscribe();

        // Act
        mockEnv.Raise(e => e.NewBrowserVersionAvailable += null, EventArgs.Empty);

        // Assert
        Assert.True(restartRequested, "shouldRestart 返回 true 时应触发重启");
    }

    [Fact]
    public void Dispose_ShouldUnsubscribe()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var callbackInvoked = false;
        Action onUpdateAvailable = () => callbackInvoked = true;

        var updater = new RuntimeUpdater(
            mockEnv.Object,
            shouldRestart: () => false,
            onUpdateAvailable: onUpdateAvailable);

        updater.Subscribe();

        // Act
        updater.Dispose();
        mockEnv.Raise(e => e.NewBrowserVersionAvailable += null, EventArgs.Empty);

        // Assert - Dispose 后事件不应再触发回调
        Assert.False(callbackInvoked, "Dispose 后回调不应被触发");
    }

    [Fact]
    public void Dispose_ShouldBeIdempotent()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var updater = new RuntimeUpdater(mockEnv.Object);
        updater.Subscribe();

        // Act & Assert - 重复 Dispose 不应抛出
        updater.Dispose();
        updater.Dispose();
    }

    [Fact]
    public void Subscribe_AfterDispose_ShouldThrow()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var updater = new RuntimeUpdater(mockEnv.Object);
        updater.Dispose();

        // Act & Assert
        Assert.Throws<ObjectDisposedException>(() => updater.Subscribe());
    }

    [Fact]
    public void Constructor_ShouldThrow_WhenEnvironmentIsNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new RuntimeUpdater(null!));
    }

    [Fact]
    public void OnNewBrowserVersionAvailable_ShouldSaveState()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var statePath = Path.Combine(Path.GetTempPath(), $"aegis-test-{Guid.NewGuid():N}.json");
        var stateStore = new RuntimeRestartStateStore(statePath);
        var updater = new RuntimeUpdater(mockEnv.Object, stateStore: stateStore);
        updater.Subscribe();

        try
        {
            // Act
            mockEnv.Raise(e => e.NewBrowserVersionAvailable += null, EventArgs.Empty);

            // Assert
            Assert.True(stateStore.HasPendingRestart(), "事件触发后应保存状态");
            var state = stateStore.LoadPendingRestart();
            Assert.NotNull(state);
            Assert.Equal("runtime-update", state.Reason);
        }
        finally
        {
            updater.Dispose();
            try { File.Delete(statePath); } catch { }
        }
    }

    [Fact]
    public void RequestControlledRestart_ShouldSaveStateAndInvokeCallback()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var statePath = Path.Combine(Path.GetTempPath(), $"aegis-test-{Guid.NewGuid():N}.json");
        var stateStore = new RuntimeRestartStateStore(statePath);
        var restartRequested = false;
        Action onRestartRequested = () => restartRequested = true;

        var updater = new RuntimeUpdater(
            mockEnv.Object,
            stateStore: stateStore,
            onRestartRequested: onRestartRequested);

        try
        {
            // Act
            updater.RequestControlledRestart();

            // Assert
            Assert.True(stateStore.HasPendingRestart(), "受控重启应保存状态");
            Assert.True(restartRequested, "应触发重启回调");
        }
        finally
        {
            updater.Dispose();
            try { File.Delete(statePath); } catch { }
        }
    }

    [Fact]
    public void RequestControlledRestart_ShouldSaveCorrectReason()
    {
        // Arrange
        var mockEnv = new Mock<CoreWebView2Environment>();
        var statePath = Path.Combine(Path.GetTempPath(), $"aegis-test-{Guid.NewGuid():N}.json");
        var stateStore = new RuntimeRestartStateStore(statePath);
        var updater = new RuntimeUpdater(mockEnv.Object, stateStore: stateStore);

        try
        {
            // Act
            updater.RequestControlledRestart();

            // Assert
            var state = stateStore.LoadPendingRestart();
            Assert.NotNull(state);
            Assert.Equal("runtime-update", state.Reason);
        }
        finally
        {
            updater.Dispose();
            try { File.Delete(statePath); } catch { }
        }
    }
}

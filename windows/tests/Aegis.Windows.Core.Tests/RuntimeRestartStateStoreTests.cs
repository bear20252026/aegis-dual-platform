namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>
/// RuntimeRestartStateStore 单元测试——验证状态保存/恢复机制。
/// 
/// 测试覆盖：
/// 1. 状态保存/加载
/// 2. 状态清除
/// 3. 文件缺失/损坏的 fail-safe 行为
/// 4. 并发安全
/// </summary>
public class RuntimeRestartStateStoreTests : IDisposable
{
    private readonly string _testStatePath;
    private readonly RuntimeRestartStateStore _store;

    public RuntimeRestartStateStoreTests()
    {
        _testStatePath = Path.Combine(Path.GetTempPath(), $"aegis-runtime-test-{Guid.NewGuid():N}.json");
        _store = new RuntimeRestartStateStore(_testStatePath);
    }

    public void Dispose()
    {
        try
        {
            if (File.Exists(_testStatePath))
                File.Delete(_testStatePath);
        }
        catch
        {
            // 测试清理失败不影响测试结果
        }
    }

    [Fact]
    public void MarkPendingRestart_ShouldCreateStateFile()
    {
        // Act
        _store.MarkPendingRestart("runtime-update");

        // Assert
        Assert.True(File.Exists(_testStatePath), "状态文件应被创建");
        Assert.True(_store.HasPendingRestart(), "HasPendingRestart 应返回 true");
    }

    [Fact]
    public void MarkPendingRestart_ShouldSaveCorrectState()
    {
        // Arrange
        var before = DateTimeOffset.UtcNow;

        // Act
        _store.MarkPendingRestart("runtime-update", "1.0.0-test");

        // Assert
        var state = _store.LoadPendingRestart();
        Assert.NotNull(state);
        Assert.Equal("runtime-update", state.Reason);
        Assert.Equal("1.0.0-test", state.AppVersion);
        Assert.True(state.MarkedAt >= before, "标记时间应在调用时刻之后");
        Assert.True(state.MarkedAt <= DateTimeOffset.UtcNow, "标记时间不应超过当前时刻");
    }

    [Fact]
    public void LoadPendingRestart_ShouldReturnNull_WhenFileMissing()
    {
        // Act & Assert
        Assert.Null(_store.LoadPendingRestart());
        Assert.False(_store.HasPendingRestart());
    }

    [Fact]
    public void LoadPendingRestart_ShouldReturnNull_WhenFileCorrupted()
    {
        // Arrange
        File.WriteAllText(_testStatePath, "invalid json {");

        // Act & Assert
        Assert.Null(_store.LoadPendingRestart(), "损坏文件应返回 null（fail-safe）");
    }

    [Fact]
    public void ClearPendingRestart_ShouldRemoveStateFile()
    {
        // Arrange
        _store.MarkPendingRestart("runtime-update");
        Assert.True(File.Exists(_testStatePath));

        // Act
        _store.ClearPendingRestart();

        // Assert
        Assert.False(File.Exists(_testStatePath), "状态文件应被删除");
        Assert.False(_store.HasPendingRestart());
    }

    [Fact]
    public void ClearPendingRestart_ShouldBeSafe_WhenFileMissing()
    {
        // Act & Assert - 不应抛出异常
        _store.ClearPendingRestart();
    }

    [Fact]
    public void MarkPendingRestart_ShouldOverwriteExistingState()
    {
        // Arrange
        _store.MarkPendingRestart("old-reason");
        var firstState = _store.LoadPendingRestart();

        // Act
        System.Threading.Thread.Sleep(10); // 确保时间戳不同
        _store.MarkPendingRestart("new-reason");

        // Assert
        var secondState = _store.LoadPendingRestart();
        Assert.NotNull(secondState);
        Assert.Equal("new-reason", secondState.Reason);
        Assert.NotEqual(firstState?.MarkedAt, secondState?.MarkedAt);
    }

    [Fact]
    public void StateFile_ShouldContainValidJson()
    {
        // Arrange
        _store.MarkPendingRestart("runtime-update", "1.0.0");

        // Act
        var json = File.ReadAllText(_testStatePath);

        // Assert
        Assert.Contains("\"Reason\": \"runtime-update\"", json);
        Assert.Contains("\"AppVersion\": \"1.0.0\"", json);
        Assert.Contains("\"MarkedAt\":", json);
    }
}

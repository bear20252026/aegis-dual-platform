namespace Aegis.Windows.Core.Tests;

using System.Windows.Input;
using Xunit;

/// <summary>C12 批（审计 2026-09-26）：MainWindow 纯函数面直测——标题截断
/// 代理对安全（CS-155）、数字键映射（CS-157）、标签循环切换索引（CS-158）。
/// 仅触达静态方法，不实例化窗口（无 STA 依赖）。</summary>
public sealed class MainWindowLogicTests
{
    // ===== CS-155：TruncateTitle =====

    [Theory]
    [InlineData("短标题", 14, "短标题")]
    [InlineData("abcdefghijklmnopqrstuvwxyz", 14, "abcdefghijklmn…")]
    public void TruncateTitle_AppendsEllipsisPastLimit(string title, int max, string expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.MainWindow.TruncateTitle(title, max));

    [Fact]
    public void TruncateTitle_NeverSplitsSurrogatePair()
    {
        // 边界恰落在代理对（😀）中间时回退一位——不产生孤立代理
        var title = new string('a', 13) + "\U0001F600" + "bc";
        var trimmed = Aegis.Windows.Chrome.MainWindow.TruncateTitle(title, 14);
        Assert.Equal(new string('a', 13) + "…", trimmed);
    }

    // ===== CS-157：ToDigit =====

    [Theory]
    [InlineData(Key.D1, 1)]
    [InlineData(Key.D9, 9)]
    [InlineData(Key.NumPad5, 5)]
    [InlineData(Key.NumPad9, 9)]
    [InlineData(Key.A, 0)]
    [InlineData(Key.D0, 0)]
    public void ToDigit_MapsNumberKeysOnly(Key key, int expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.MainWindow.ToDigit(key));

    // ===== CS-158：NextIndex =====

    [Theory]
    [InlineData(0, 1, 3, 1)]    // 常规前进
    [InlineData(2, 1, 3, 0)]    // 尾部环绕到首
    [InlineData(0, -1, 3, 2)]   // 首部反向环绕到尾
    [InlineData(-1, 1, 3, 1)]   // 未找到/负索引钳 0 起算
    [InlineData(4, 1, 3, 2)]    // 越界索引按取模环绕
    public void NextIndex_CyclesAndClamps(int current, int direction, int count, int expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.MainWindow.NextIndex(current, direction, count));
}

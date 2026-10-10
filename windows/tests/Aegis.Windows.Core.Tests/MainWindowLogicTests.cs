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

    // ===== C19b 批（审计 2026-09-26）：CS-292 新窗口链接判定 =====
    // 第九轮定稿项 5：判定与文案单源 Core.NewTabGate——此前主窗内联一份、
    // 无痕窗另有一份 CanOpenNewWindowLink（靠这条用例证明两者同口径）。
    // 现在两窗调用同一个方法，"同口径"由构造保证，本用例改钉该单源的向量。

    [Theory]
    [InlineData("https://example.com/page", true)]     // 公网放行
    [InlineData("http://127.0.0.1:8080/dev", true)]    // 本机放行（本地开发）
    [InlineData("http://localhost/x", true)]           // 本机域名放行
    [InlineData("file:///C:/Windows/system32", false)] // 非导航协议拒绝
    [InlineData("javascript:alert(1)", false)]         // 脚本协议拒绝
    [InlineData("http://192.168.1.1/admin", true)]     // 内网设备放行（B8 裁决）
    [InlineData("http://169.254.169.254/latest/meta-data/", false)] // 元数据拒绝
    [InlineData(null, false)]
    [InlineData("", false)]
    [InlineData("not a url", false)]
    public void NewTabGate_AddressBoundaryVectors(string? url, bool expected)
    {
        var decision = new Aegis.Windows.Core.NewTabGate()
            .Decide("tab-1", url, 1_000_000L);
        Assert.Equal(expected, decision == Aegis.Windows.Core.NewTabGate.NewTabDecision.Open);
        if (!expected)
        {
            // 边界拒绝的文案必须带 reserved_address（拒绝码单源，B4「可见拒绝」口径）
            Assert.Contains(
                Aegis.Windows.Broker.ReservedAddressBoundary.DenyCode,
                Aegis.Windows.Core.NewTabGate.RejectionFor(decision));
        }
    }
}

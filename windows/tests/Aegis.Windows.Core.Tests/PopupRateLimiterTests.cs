namespace Aegis.Windows.Core.Tests;

using Aegis.Windows;
using Xunit;

/// <summary>第九轮 R9-CS-5：崩溃弹窗频控器的冷启动判据。
///
/// 被消除的形态：槽位以 **0** 起步而判定是 `nowTicks - _ticks[i] >= windowMs`，
/// 调用方传 `Environment.TickCount64`（自开机起毫秒）⇒ 开机后第一个窗口里
/// `nowTicks` 本身就小于 windowMs，三槽全判「未到期」⇒ 这段时间所有崩溃弹窗被
/// 静默拒（只记日志）。它管异常提示、方向保守所以从未被当成缺陷暴露；真正的风险是
/// **形状被抄走**——同形状用在「拒绝用户可达的功能」上就是打开即失效
/// （Core/NewTabGate.cs 的 SlotWindow 就是刻意避开这一课的孪生）。
///
/// 时钟全部注入，逐毫秒确定，不靠 sleep。</summary>
public sealed class PopupRateLimiterTests
{
    private const long WindowMs = 30_000L;

    [Fact]
    public void ColdStart_AllowsFullQuotaInsideFirstWindow()
    {
        // 开机后 1 秒（now < windowMs）——旧实现在这里第一次调用就返回 false。
        var limiter = new PopupRateLimiter(3);
        Assert.True(limiter.ShouldShow(1_000L, WindowMs), "冷启动第一次必须放行（弹窗是唯一的可见信号）");
        Assert.True(limiter.ShouldShow(1_001L, WindowMs), "配额内第 2 次仍须放行");
        Assert.True(limiter.ShouldShow(1_002L, WindowMs), "配额内第 3 次仍须放行");
        Assert.False(limiter.ShouldShow(1_003L, WindowMs), "超出配额必须静默——频控本身不能失效");
    }

    [Fact]
    public void ZeroTickCountAtBootStillAllowsFirstPopup()
    {
        // nowTicks = 0 正是旧形状彻底静默的那个时刻；哨兵比较必须先于减法
        // （`0 - long.MinValue` 会溢出）。
        var limiter = new PopupRateLimiter(1);
        Assert.True(limiter.ShouldShow(0L, WindowMs));
        Assert.False(limiter.ShouldShow(1L, WindowMs));
    }

    [Fact]
    public void WindowElapse_FreesExactlyOneSlot()
    {
        var limiter = new PopupRateLimiter(2);
        Assert.True(limiter.ShouldShow(10_000L, WindowMs));
        Assert.True(limiter.ShouldShow(10_500L, WindowMs));
        Assert.False(limiter.ShouldShow(11_000L, WindowMs));
        // 第一槽到期（10_000 + 30_000）⇒ 放行一次；第二槽仍在窗口内 ⇒ 立刻再拒。
        Assert.True(limiter.ShouldShow(40_000L, WindowMs));
        Assert.False(limiter.ShouldShow(40_100L, WindowMs));
    }

    [Fact]
    public void RollingRecovery_KeepsQuotaOverTime()
    {
        // 长期运行的形态：每过一个窗口恢复一槽，配额不被永久占用。
        var limiter = new PopupRateLimiter(1);
        Assert.True(limiter.ShouldShow(1_000L, WindowMs));
        Assert.True(limiter.ShouldShow(31_000L, WindowMs));
        Assert.True(limiter.ShouldShow(61_000L, WindowMs));
        Assert.False(limiter.ShouldShow(61_500L, WindowMs));
    }

    [Fact]
    public void ClockWrapBeyondFirstUse_IsJudgedByElapsedWindow()
    {
        // 真实 TickCount64 在「已开机数日」的机器上远大于 windowMs——首次调用
        // 必须放行（旧实现也放行，这条钉住修复没有把常态路径改坏）。
        var limiter = new PopupRateLimiter(3);
        var upForDays = 4L * 24 * 3_600_000;
        Assert.True(limiter.ShouldShow(upForDays, WindowMs));
        Assert.True(limiter.ShouldShow(upForDays + 1, WindowMs));
        Assert.True(limiter.ShouldShow(upForDays + 2, WindowMs));
        Assert.False(limiter.ShouldShow(upForDays + 3, WindowMs));
    }
}

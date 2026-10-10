namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Broker;
using Aegis.Windows.Core;
using Xunit;

/// <summary>第九轮定稿项 5（第八轮 §七 遗留）：页面驱动的「新建标签」通道闸门。
///
/// 补的缺口：HostWebView 把 NewWindowRequested 一律 Handled 后转给宿主，宿主直接
/// NewTab，而 Windows 侧全仓没有任何标签数上限（TabManager.NewTab 无条件插入）——
/// 一个循环 window.open 的页面即可无上限开标签，即 CS-382 同族的「页面耗尽宿主资源」。
///
/// 时钟全部注入（真实实现传 Environment.TickCount64），所以「窗口内第 4 次拒」
/// 「窗口滑过后恢复」这类判据是逐毫秒确定的，不靠 sleep。</summary>
public sealed class NewTabGateTests
{
    private const string PublicTarget = "https://example.com/page";
    private const string ReservedTarget = "http://169.254.169.254/latest/meta-data/";
    private const long T0 = 1_000_000L;
    private const string TabA = "tab-a";
    private const string TabB = "tab-b";

    // ===== 配额本身 =====

    [Fact]
    public void ColdStart_AllowsFullQuotaInsideOneWindow()
    {
        // 冷启动第一次必须放行：槽位以「从未占用」起步。PopupRateLimiter 同形状的
        // 实现以 0 起步，开机后第一个窗口内 (now-0 < windowMs) 恒真 ⇒ 全拒（那条
        // 只管崩溃弹窗、方向保守才没暴露）。这条用例就是防本台复制那个缺陷。
        var gate = new NewTabGate();
        for (var i = 0; i < NewTabGate.MaxPerWindow; i++)
        {
            Assert.Equal(NewTabGate.NewTabDecision.Open, gate.Decide(TabA, PublicTarget, T0));
        }
    }

    [Fact]
    public void RequestBeyondQuota_InSameWindow_IsBlockedWithCode()
    {
        var gate = new NewTabGate();
        for (var i = 0; i < NewTabGate.MaxPerWindow; i++)
        {
            gate.Decide(TabA, PublicTarget, T0);
        }

        var decision = gate.Decide(TabA, PublicTarget, T0 + 1_000L);
        Assert.Equal(NewTabGate.NewTabDecision.BlockedByRateLimit, decision);
        Assert.Contains(NewTabGate.RateLimitCode, NewTabGate.RejectionFor(decision));
    }

    [Fact]
    public void Quota_ReturnsAfterWholeWindowElapses()
    {
        var gate = new NewTabGate();
        for (var i = 0; i < NewTabGate.MaxPerWindow; i++)
        {
            gate.Decide(TabA, PublicTarget, T0);
        }

        Assert.Equal(NewTabGate.NewTabDecision.BlockedByRateLimit, gate.Decide(TabA, PublicTarget, T0 + NewTabGate.WindowMs - 1));
        Assert.Equal(NewTabGate.NewTabDecision.Open, gate.Decide(TabA, PublicTarget, T0 + NewTabGate.WindowMs));
    }

    // ===== 键的粒度：按来源标签，不是全窗口 =====

    [Fact]
    public void OneTabFlooding_DoesNotStarveAnotherTab()
    {
        var gate = new NewTabGate();
        for (var i = 0; i < NewTabGate.MaxPerWindow; i++)
        {
            gate.Decide(TabA, PublicTarget, T0);
        }

        Assert.Equal(NewTabGate.NewTabDecision.BlockedByRateLimit, gate.Decide(TabA, PublicTarget, T0));
        // 键是「来源标签」而不是窗口/应用：恶意页的洪水不能把别的标签一起饿死。
        Assert.Equal(NewTabGate.NewTabDecision.Open, gate.Decide(TabB, PublicTarget, T0));
    }

    // ===== 顺序即口径：地址边界在前，且不烧配额 =====

    [Fact]
    public void AddressBoundary_IsJudgedFirst_AndDoesNotConsumeQuota()
    {
        var gate = new NewTabGate();
        for (var i = 0; i < 4 * NewTabGate.MaxPerWindow; i++)
        {
            Assert.Equal(NewTabGate.NewTabDecision.BlockedByAddressBoundary, gate.Decide(TabA, ReservedTarget, T0));
        }

        // 恶意页拿保留地址刷不出限流：配额一分没动，公开目标仍放行。
        Assert.Equal(NewTabGate.NewTabDecision.Open, gate.Decide(TabA, PublicTarget, T0));
    }

    [Fact]
    public void AddressBoundary_Rejection_CarriesTheSingleSourceDenyCode()
    {
        var message = NewTabGate.RejectionFor(NewTabGate.NewTabDecision.BlockedByAddressBoundary);
        Assert.Contains(ReservedAddressBoundary.DenyCode, message);
        Assert.DoesNotContain(NewTabGate.RateLimitCode, message);
    }

    [Fact]
    public void RateLimitCode_IsSingleSourceLiteral() =>
        Assert.Equal("new_tab_rate_limited", NewTabGate.RateLimitCode);

    // ===== 字典规模不得跟随历史标签数（拒绝面不能变成第二个无界结构） =====

    [Fact]
    public void TrackedTabs_FollowCurrentTabs_NotHistory()
    {
        var gate = new NewTabGate();
        long now = T0;
        for (var round = 0; round < 4; round++)
        {
            for (var i = 0; i < NewTabGate.PruneAtTrackedTabs + 8; i++)
            {
                Assert.Equal(NewTabGate.NewTabDecision.Open, gate.Decide($"tab-{round}-{i}", PublicTarget, now));
            }

            now += NewTabGate.WindowMs;   // 下一轮的所有来源都已整窗过期
        }

        // 四轮共 288 个来源标签，但每满阈值就回收过期条目 ⇒ 规模不跟随历史总数。
        // 去掉 PruneFullyExpired 调用这条即红（实测口径：无界计数结构就是第二个耗尽面）。
        Assert.True(
            gate.TrackedTabs <= NewTabGate.PruneAtTrackedTabs + 8,
            $"计数字典随历史标签无界增长：TrackedTabs={gate.TrackedTabs}");
    }

    [Fact]
    public void Forget_ReleasesTrackedTab()
    {
        var gate = new NewTabGate();
        for (var i = 0; i < NewTabGate.MaxPerWindow; i++)
        {
            gate.Decide(TabA, PublicTarget, T0);
        }

        Assert.Equal(NewTabGate.NewTabDecision.BlockedByRateLimit, gate.Decide(TabA, PublicTarget, T0));
        gate.Forget(TabA);
        Assert.Equal(NewTabGate.NewTabDecision.Open, gate.Decide(TabA, PublicTarget, T0));
    }
}

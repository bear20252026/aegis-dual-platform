namespace Aegis.Windows.Core.Tests;

using System;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>后台标签睡眠策略单测（上帝对象拆分·第五批）——固定/已睡/激活/
/// 闲置未到阈值/无 runtime 各自跳过，阈值取闭区间（&gt;=），关闭阈值全跳过。</summary>
public class TabSleepPolicyTests
{
    private static Tab MakeTab(string id, bool pinned = false, bool sleeping = false, DateTime? last = null)
    {
        var tab = new Tab(id, "https://example.com") { IsPinned = pinned, IsSleeping = sleeping };
        if (last is not null)
            tab.LastActivated = last.Value;
        return tab;
    }

    [Fact]
    public void Disabled_WhenSleepMinutesNotPositive()
    {
        var now = DateTime.Now;
        var tabs = new[] { MakeTab("a", last: now.AddHours(-5)) };
        Assert.Empty(TabSleepPolicy.SelectTabsToSleep(tabs, activeTabId: null, 0, now, _ => true));
        Assert.Empty(TabSleepPolicy.SelectTabsToSleep(tabs, activeTabId: null, -1, now, _ => true));
    }

    [Fact]
    public void SleepsIdleBackgroundTabWithRuntime()
    {
        var now = DateTime.Now;
        var idle = MakeTab("a", last: now.AddMinutes(-30));
        var result = TabSleepPolicy.SelectTabsToSleep(new[] { idle }, "other", 10, now, _ => true);
        Assert.Equal("a", Assert.Single(result).TabId);
    }

    [Fact]
    public void SkipsPinned_Sleeping_Active_AndNoRuntime()
    {
        var now = DateTime.Now;
        var old = now.AddMinutes(-30);
        var pinned = MakeTab("pinned", pinned: true, last: old);
        var sleeping = MakeTab("asleep", sleeping: true, last: old);
        var active = MakeTab("active", last: old);
        var runtimeless = MakeTab("runtimeless", last: old);
        var result = TabSleepPolicy.SelectTabsToSleep(
            new Tab[] { pinned, sleeping, active, runtimeless },
            "active", 10, now,
            tabId => tabId != "runtimeless");
        Assert.Empty(result);
    }

    [Fact]
    public void Threshold_IsInclusive()
    {
        var now = DateTime.Now;
        // 恰好到达阈值（>= 语义）入睡；差 1 秒未到不睡
        var exactly = MakeTab("exactly", last: now.AddMinutes(-10));
        var almost = MakeTab("almost", last: now.AddMinutes(-10).AddSeconds(1));
        var result = TabSleepPolicy.SelectTabsToSleep(
            new[] { exactly, almost }, "other", 10, now, _ => true);
        Assert.Equal("exactly", Assert.Single(result).TabId);
    }
}

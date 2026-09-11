namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Linq;
using Aegis.Windows.Core.Tabs;

/// <summary>后台标签睡眠策略（上帝对象拆分·第五批）：巡检决策纯函数化——
/// 选出「非固定 + 未睡 + 非激活 + 闲置超阈值 + 存在 runtime」的标签。
/// 编排（计时器/真正入睡副作用）留在 MainWindow，决策边界在此可单测。</summary>
public static class TabSleepPolicy
{
    /// <summary>返回本次巡检应入睡的标签（调用方负责 Sleep 副作用与
    /// IsSleeping 标记）。sleepMinutes &lt;= 0 视为功能关闭。</summary>
    public static IReadOnlyList<Tab> SelectTabsToSleep(
        IReadOnlyList<Tab> tabs,
        string? activeTabId,
        int sleepMinutes,
        DateTime now,
        Func<string, bool> hasRuntime)
    {
        if (sleepMinutes <= 0)
            return Array.Empty<Tab>();
        return tabs
            .Where(tab => !tab.IsPinned
                && !tab.IsSleeping
                && tab.TabId != activeTabId
                && (now - tab.LastActivated).TotalMinutes >= sleepMinutes
                && hasRuntime(tab.TabId))
            .ToList();
    }
}

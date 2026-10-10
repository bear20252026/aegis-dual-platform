namespace Aegis.Windows.Core;

using System;
using System.Collections.Generic;

/// <summary>页面驱动的「新建标签」通道闸门（主窗与无痕窗共用单源）。
///
/// 补的是什么：宿主对 NewWindowRequested 一律 Handled 后把 URL 转发给自己
/// （CS-292），而两个宿主都直接 NewTab——**Windows 侧全仓没有任何标签数上限**
/// （Core/Tabs/TabManager.cs 的 NewTab 无条件插入；Android 的 maxActive=8 是
/// 「挂起最久未用」而不是「拒绝」）。于是恶意页里一句循环 window.open 就能无上限
/// 开标签：每个标签一套 WebView2 运行时 + 一个 broker session，即 CS-382 同族的
/// 「页面耗尽宿主资源」形态——用户看到的是浏览器卡死，而不是某个链接失败。
///
/// 口径（第八轮 §七 定稿项 5）：**同一来源标签 10 秒内最多 3 次**。
/// • 按「来源标签」计数而不是全窗口/全应用：一个页面的洪水不能把用户其它标签的
///   新开链接一起饿死。NewWindowRequested 逐 runtime 订阅，tab.TabId 即天然键。
/// • 拒绝必须可见（第七轮 B4）：宿主用 RejectionFor 的文案走各自呈现通道
///   （主窗横幅 / 无痕窗安全日志），文案带拒绝码，与 reserved_address 同名单源。
/// • 不做「非用户手势一律拒」：事件载荷只有 URL 字符串，拿不到 WebView2 的
///   IsUserInitiated，改签名会牵动两窗接线与既有测试——那是产品行为变更，不是补漏。
///
/// 时钟一律由调用方注入（Environment.TickCount64）⇒ 纯判定可测。与
/// PopupRateLimiter（App.xaml.cs:11）同算法而**不同生死**：那台的槽位以 0 起步，
/// 开机后第一个窗口内 (now - 0 &lt; windowMs) 恒真 ⇒ 所有请求都被拒；它管崩溃弹窗，
/// 方向保守所以从未暴露。本台的槽位以「从未占用」起步，冷启动首次必然放行——
/// 这条有专门用例（冷启动豁免）。</summary>
internal sealed class NewTabGate
{
    /// <summary>限流窗口与配额（定稿值：10 秒 / 每来源标签 3 次）。</summary>
    internal const long WindowMs = 10_000;
    internal const int MaxPerWindow = 3;

    /// <summary>限流面的拒绝码单源。地址边界那条不在这里造第二份——它由
    /// Broker.ReservedAddressBoundary.DenyCode 持有（本文件只引用）。</summary>
    internal const string RateLimitCode = "new_tab_rate_limited";

    /// <summary>字典规模的下界维护阈值：洪水场景下标签本身可能被无限开，
    /// 计数字典不能成为第二个无界结构（CS-333「下载集合有界」同款顾虑）。
    /// 到阈值就回收「整窗都已过期」的条目——过期条目不再影响任何判定，删它无损语义；
    /// 于是字典规模跟随**当前**标签数，而不是跟随历史标签总数。</summary>
    internal const int PruneAtTrackedTabs = 64;

    /// <summary>WebView2 事件可能不在 UI 线程回调（本文件两窗的既有接线都用
    /// Dispatcher.BeginInvoke 即为证据），故判定自带互斥。</summary>
    private readonly object _gate = new();

    private readonly Dictionary<string, SlotWindow> _perTab = new();

    /// <summary>一条页面发起的新窗口请求的终态判定。顺序即口径：先地址边界
    /// （保留地址根本不该打开，也不该消耗限流配额），再限流。</summary>
    public NewTabDecision Decide(string tabId, string? targetUrl, long nowTicks)
    {
        if (!UrlSafety.CanOpenHttpUrl(targetUrl))
        {
            return NewTabDecision.BlockedByAddressBoundary;
        }

        lock (_gate)
        {
            return TryAcquireSlot(tabId, nowTicks)
                ? NewTabDecision.Open
                : NewTabDecision.BlockedByRateLimit;
        }
    }

    /// <summary>呈现文案单源（横幅还是日志由宿主决定，文本不在两处重写）。</summary>
    public static string RejectionFor(NewTabDecision decision) =>
        decision switch
        {
            // 主窗原文案逐字保留，只是搬进单源并补上拒绝码（R8-CS-SEC-06 落地的措辞）。
            NewTabDecision.BlockedByAddressBoundary =>
                $"已拒绝打开该链接（链路本地/云元数据/保留地址） code={Broker.ReservedAddressBoundary.DenyCode}",
            _ =>
                $"新窗口请求过于频繁，已拒绝（{WindowMs / 1000} 秒内每标签最多 {MaxPerWindow} 次） code={RateLimitCode}",
        };

    /// <summary>标签关闭时宿主可显式回收；不调用也不无界（见 PruneAtTrackedTabs）。</summary>
    public void Forget(string tabId)
    {
        lock (_gate)
        {
            _ = _perTab.Remove(tabId);
        }
    }

    /// <summary>测试缝：当前跟踪的来源标签数。生产路径不读它——它存在的唯一目的是
    /// 让「字典规模跟随当前标签数、不跟随历史标签总数」这条判据可被断言
    /// （限流语义下过期条目本就不影响判定，没有这个读数就无法证伪无界增长）。</summary>
    internal int TrackedTabs
    {
        get
        {
            lock (_gate)
            {
                return _perTab.Count;
            }
        }
    }

    private bool TryAcquireSlot(string tabId, long nowTicks)
    {
        if (!_perTab.TryGetValue(tabId, out var window))
        {
            if (_perTab.Count >= PruneAtTrackedTabs)
            {
                PruneFullyExpired(nowTicks);
            }

            window = new SlotWindow();
            _perTab[tabId] = window;
        }

        return window.TryAcquire(nowTicks, WindowMs);
    }

    private void PruneFullyExpired(long nowTicks)
    {
        // 遍历时不能改字典（InvalidOperationException），先收键再删。
        List<string>? stale = null;
        foreach (var (tabId, window) in _perTab)
        {
            if (window.AllSlotsExpired(nowTicks, WindowMs))
            {
                (stale ??= new List<string>()).Add(tabId);
            }
        }

        if (stale is not null)
        {
            foreach (var tabId in stale)
            {
                _ = _perTab.Remove(tabId);
            }
        }
    }

    /// <summary>判定终态（枚举而不是 bool：拒绝有两种，文案与拒绝码都不同）。</summary>
    internal enum NewTabDecision
    {
        Open,
        BlockedByAddressBoundary,
        BlockedByRateLimit,
    }

    /// <summary>槽位式滑动窗口：每个槽记一次放行时刻；有空槽（或槽已过期）即占用并
    /// 放行，全槽都在窗口内即拒。</summary>
    private sealed class SlotWindow
    {
        private const long NeverUsed = long.MinValue;

        private readonly long[] _ticks = CreateUnused();

        private static long[] CreateUnused()
        {
            var ticks = new long[MaxPerWindow];
            Array.Fill(ticks, NeverUsed);
            return ticks;
        }

        public bool TryAcquire(long nowTicks, long windowMs)
        {
            for (var i = 0; i < _ticks.Length; i++)
            {
                if (_ticks[i] == NeverUsed || nowTicks - _ticks[i] >= windowMs)
                {
                    _ticks[i] = nowTicks;
                    return true;
                }
            }

            return false;
        }

        public bool AllSlotsExpired(long nowTicks, long windowMs)
        {
            for (var i = 0; i < _ticks.Length; i++)
            {
                if (_ticks[i] != NeverUsed && nowTicks - _ticks[i] < windowMs)
                {
                    return false;
                }
            }

            return true;
        }
    }
}

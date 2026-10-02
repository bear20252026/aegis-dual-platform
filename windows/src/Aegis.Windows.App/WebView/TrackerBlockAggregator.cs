namespace Aegis.Windows.WebView;

using System;
using System.Collections.Generic;

/// <summary>CS-363（2026-10-01 审计）：拦截类事件聚合提纯——此前聚合逻辑
/// 内联在 HostWebView（字典 + 计数 + 阈值落盘），零测试覆盖。本类只做
/// 聚合/阈值/清空三件事，不含落盘副作用（HostWebView 注入写出行）。
/// 调用方在创建控件的 UI 线程触发——单线程访问，无需加锁。</summary>
internal sealed class TrackerBlockAggregator
{
    /// <summary>累计满阈值次拦截即提示调用方落盘一次（替代逐请求落盘）。</summary>
    internal const int DefaultFlushThreshold = 50;

    private readonly int _flushThreshold;
    private readonly Dictionary<string, (int Count, string Detail)> _aggregates =
        new(StringComparer.OrdinalIgnoreCase);
    private int _pendingSinceFlush;

    public TrackerBlockAggregator(int flushThreshold = DefaultFlushThreshold) =>
        _flushThreshold = Math.Max(1, flushThreshold);

    /// <summary>累计未落盘的拦截次数（调用方 Dispose 兜底清空判定用）。</summary>
    public int PendingCount => _pendingSinceFlush;

    /// <summary>记录一次拦截（按 host 聚合计数；detail 取首次形态）。
    /// 返回 true = 已达阈值，调用方应立即 Drain 落盘。</summary>
    public bool Record(string host, string detail)
    {
        if (_aggregates.TryGetValue(host, out var existing))
            _aggregates[host] = (existing.Count + 1, existing.Detail);
        else
            _aggregates[host] = (1, detail);
        return ++_pendingSinceFlush >= _flushThreshold;
    }

    /// <summary>取走全部聚合行并清零计数（落盘与 Dispose 兜底共用）。</summary>
    public IReadOnlyList<(string Host, int Count, string Detail)> Drain()
    {
        var rows = new List<(string, int, string)>(_aggregates.Count);
        foreach (var pair in _aggregates)
            rows.Add((pair.Key, pair.Value.Count, pair.Value.Detail));
        _aggregates.Clear();
        _pendingSinceFlush = 0;
        return rows;
    }
}

namespace Aegis.Windows.WebView;

using System;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>HostWebView 的「拦截事件如何落盘」接线（CS-308/CS-363 的落盘侧），
/// 自 HostWebView.cs 移入以守单文件行数红线——判定与 403 仍在主文件，本分片
/// 只做按 host 聚合计数与周期性 flush。partial 同类型：字段与 Dispose 仍共作用域。</summary>
public sealed partial class HostWebView
{
    // —— CS-308（2026-09-26 审计）：拦截类事件聚合落盘 ——
    // 跟踪器密集页此前每个被拦截子请求同步 SecurityLog.Write（每条
    // File.AppendAllText）——IO 放大且 1MB 取证日志被冲掉。按 host 聚合计数，
    // 周期性（累计 BlockAggregateFlushThreshold 次）落一行；Dispose 兜底清空。
    // CS-363（2026-10-01 审计）：聚合逻辑提纯到 TrackerBlockAggregator
    //（单测直测聚合/阈值/尾部 flush），HostWebView 只保留落盘接线。
    private readonly TrackerBlockAggregator _trackerBlocks = new(BlockAggregateFlushThreshold);

    private const int BlockAggregateFlushThreshold = TrackerBlockAggregator.DefaultFlushThreshold;

    private void RecordTrackerBlock(Uri uri, int level, CoreWebView2WebResourceContext context)
    {
        if (_trackerBlocks.Record(uri.Host, $"级别{level} ctx={context}"))
            FlushTrackerBlocks();
    }

    private void FlushTrackerBlocks()
    {
        foreach (var row in _trackerBlocks.Drain())
        {
            SecurityLog.Write(
                $"[privacy] 跟踪防护拦截聚合: {row.Host} ×{row.Count}（{row.Detail}）");
        }
    }
}

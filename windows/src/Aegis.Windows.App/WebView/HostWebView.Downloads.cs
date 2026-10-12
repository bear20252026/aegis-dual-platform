namespace Aegis.Windows.WebView;

using System;
using System.Collections.Generic;
using System.IO;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>HostWebView 的下载分片（R9-B37，第九轮队列 Q24）：授权判定、在途登记表
/// 及其生命周期。从 HostWebView.cs 移入有两个理由，第二个是本次的实际修复：
///
/// 旧形态是「放行后 `_trackedDownloads.Add(operation)`，完成**从不移除**」——只有
/// `UnwireEvents` 里一次 `Clear()`。后果有两层：①长会话里已结束的
/// `CoreWebView2DownloadOperation` COM 引用（连同其内部 WebView2 指针）一直堆着，
/// 每标签每文件一个，永不归还；②`StopLiveTraffic` 对整张表逐个 `Cancel()`，
/// 已结束项必抛——旧代码靠 `catch` 吞掉，于是「取消失败」既是噪声又不是语义，
/// 谁也不知道那一步到底取消了几个真在途的下载。
///
/// 现口径：登记时订阅 `StateChanged`（本 SDK 1.0.2903.40 上 `CoreWebView2DownloadOperation`
/// 只有 BytesReceivedChanged / EstimatedEndTimeChanged / StateChanged 三个事件，
/// **没有** Win32 面那个 Completed——反射实测确认），状态进终态即摘除引用并退订；
/// 终止路径只对在途项 `Cancel()`。
///
/// `State` 读取本身也可能抛（内核已销毁），所以「读不到状态」按**非终态**处理：
/// 这条与旧的「一律 Cancel 再吞异常」相反——真在途的下载不能被 COM 抖动放过，
/// 而重复 Cancel 一只已结束的项除了制造被吞掉的异常什么都没有。
///
/// partial 同类型：字段与 Dispose 仍共作用域。</summary>
public sealed partial class HostWebView
{
    private readonly object _downloadsLock = new();
    private readonly List<CoreWebView2DownloadOperation> _trackedDownloads = new();

    // 命名处理器（与主文件的 _onXxx 同一纪律）：匿名闭包不可退订，
    // 而这里的退订是回收 COM 引用的必经一步。事件参数类型在本 SDK 是 `object`
    // （反射实测：StateChanged : EventHandler`1[[System.Object]]），不是强类型 args。
    private EventHandler<object>? _onDownloadStateChanged;

    /// <summary>M3 下载管理（ADR-009）：全量经 broker 审计；危险扩展（对齐
    /// Android DownloadPolicy）需用户显式确认——无确认订阅者时 fail-closed 拒绝。</summary>
    private void OnDownloadStarting(CoreWebView2DownloadStartingEventArgs e)
    {
        var downloadUrl = string.Empty;
        var suggested = string.Empty;
        var metadataReadable = true;
        try
        {
            downloadUrl = e.DownloadOperation?.Uri ?? string.Empty;
            // SDK 1.0.2903.40 无 SuggestedFileName——从结果路径提取
            suggested = Path.GetFileName(e.DownloadOperation?.ResultFilePath ?? string.Empty);
        }
        catch (Exception)
        {
            metadataReadable = false;
        }
        // 审计第六轮（2026-10-03）：元数据**就是**策略输入，不是可忽略的旁路。
        // 此前读取失败被吞成空串——SanitizeFileName("") 得 benign 默认名、
        // RequiresExplicitConfirmation("","aegis_download") 判非危险、
        // AllowDownload(session,tab,"",…) 因会话仍在而返回 true，于是 COM 抖动
        // 一次就让 Content-Disposition: evil.exe 静默落盘（fail-open）。
        // 现口径：读不到 / 无 URL / 无操作对象 = 按危险处理，无确认订阅者即拒。
        if (string.IsNullOrEmpty(downloadUrl))
            metadataReadable = false;
        var fileName = metadataReadable
            ? Core.Downloads.DownloadPolicy.SanitizeFileName(suggested)
            : string.Empty;
        var dangerous = !metadataReadable
            || Core.Downloads.DownloadPolicy.RequiresExplicitConfirmation(downloadUrl, fileName);
        if (dangerous
            && (DownloadConfirmationRequested is null
                || !DownloadConfirmationRequested.Invoke(downloadUrl, fileName)))
        {
            Refuse(e, downloadUrl);
            return;
        }
        // 下载门禁真正生效：AllowDownload 校验会话/标签/kill-switch，
        // 返回值接入实际放行——此前被忽略（ADR-002 审计发现 G）。
        // 非危险下载或危险已确认，都必须过这道门。
        var allowed = _broker.AllowDownload(_sessionId, _tabId, downloadUrl, fileName, dangerous);
        if (!allowed)
        {
            Refuse(e, downloadUrl);
            return;
        }
        // 审计第六轮（2026-10-03）：放行后登记在途下载，供紧急终止取消——
        // 入口判定只能挡新的副作用请求，已开始的下载不会自行停下。
        if (e.DownloadOperation is { } operation)
            TrackDownload(operation);
    }

    /// <summary>拒绝路径（两处判定合一）：`Handled` 保证拒绝语义，`Cancel` 只是尽力——
    /// 操作可能尚未启动，抛出不改变任何东西。</summary>
    private void Refuse(CoreWebView2DownloadStartingEventArgs e, string downloadUrl)
    {
        e.Handled = true;
        try
        {
            e.DownloadOperation?.Cancel();
        }
        catch (Exception)
        {
            // 操作可能尚未启动——拒绝语义已由 Handled 保证
        }
        _broker.DenyDownload(_sessionId, _tabId, downloadUrl);
    }

    /// <summary>登记一只在途下载，并订阅它的状态变化以便终态摘除（Q24 的修复本体）。</summary>
    private void TrackDownload(CoreWebView2DownloadOperation operation)
    {
        // 方法组只转成一个逻辑委托（按 target+method 相等），所以所有 operation
        // 共用这一个处理器是安全的——sender 就是事件源本身。
        _onDownloadStateChanged ??= (sender, _) =>
            RetireDownloadIfTerminal(sender as CoreWebView2DownloadOperation);
        operation.StateChanged += _onDownloadStateChanged;
        lock (_downloadsLock)
            _trackedDownloads.Add(operation);
        // 订阅之前就已经结束的（快文件 + 慢接线）不会再有事件——不补这一刀就是永久滞留项。
        RetireDownloadIfTerminal(operation);
    }

    /// <summary>终态才摘（Completed / Interrupted）；非终态与读不到状态都不动表。</summary>
    private void RetireDownloadIfTerminal(CoreWebView2DownloadOperation? operation)
    {
        if (operation is not null && IsTerminal(operation))
            RetireDownload(operation);
    }

    /// <summary>终态摘除：退订 + 丢弃 COM 引用。可重复调用（第二次是无事）。</summary>
    private void RetireDownload(CoreWebView2DownloadOperation operation)
    {
        try
        {
            operation.StateChanged -= _onDownloadStateChanged;
        }
        catch (Exception)
        {
            // 内核已销毁时退订也会抛——引用照旧要摘
        }
        lock (_downloadsLock)
            _trackedDownloads.Remove(operation);
    }

    /// <summary>是否已到终态（Completed/Interrupted）。**读不到状态按非终态处理**——
    /// 这个方向的保守是给终止路径用的：宁可多做一次 Cancel（抛→吞），
    /// 也不要因为 COM 抖动而放过一只真在途的下载。</summary>
    private static bool IsTerminal(CoreWebView2DownloadOperation operation)
    {
        try
        {
            return IsTerminalState(operation.State);
        }
        catch (Exception)
        {
            // 内核已销毁——读不到状态就按非终态处理（终止路径仍会 Cancel 一次）
            return false;
        }
    }

    /// <summary>CS-329 同款口径：`CoreWebView2DownloadOperation` 无法在单测构造
    /// （internal ctor），所以终态判定本身提成 internal static 纯函数直测；
    /// 上面那层 try/catch 只负责 COM 抛出的形状。</summary>
    internal static bool IsTerminalState(CoreWebView2DownloadState state) => state switch
    {
        CoreWebView2DownloadState.Completed => true,
        CoreWebView2DownloadState.Interrupted => true,
        _ => false,
    };

    /// <summary>紧急终止反应的一支（由 `StopLiveTraffic` 调用）：只取消仍在途的下载。</summary>
    private void CancelInFlightDownloads()
    {
        CoreWebView2DownloadOperation[] snapshot;
        lock (_downloadsLock)
            snapshot = _trackedDownloads.ToArray();
        foreach (var download in snapshot)
        {
            if (!IsTerminal(download))
            {
                try
                {
                    download.Cancel();
                }
                catch (Exception)
                {
                    // 取消与终态事件并发——语义已由入口判定与 Handled 保证
                }
            }
            // 终止之后一律摘表：这一支不依赖 StateChanged 还会不会来（内核被 Stop 之后
            // 事件面并不保证），而表不清零就是 Q24 原来那个滞留形态。
            RetireDownload(download);
        }
    }

    /// <summary>解绑时丢弃全部在途引用（`UnwireEvents` 调）——退订先行，
    /// 否则表清掉了、事件源还攥着本实例的委托。</summary>
    private void ReleaseTrackedDownloads()
    {
        CoreWebView2DownloadOperation[] snapshot;
        lock (_downloadsLock)
        {
            snapshot = _trackedDownloads.ToArray();
            _trackedDownloads.Clear();
        }
        foreach (var download in snapshot)
        {
            try
            {
                download.StateChanged -= _onDownloadStateChanged;
            }
            catch (Exception)
            {
                // 内核已销毁——引用已经丢弃，退订失败不再有任何后果
            }
        }
    }
}

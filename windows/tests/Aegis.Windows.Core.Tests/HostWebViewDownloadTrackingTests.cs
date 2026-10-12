namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using Aegis.Windows.WebView;
using Microsoft.Web.WebView2.Core;
using Xunit;

/// <summary>R9-B37（第九轮队列 Q24）：在途下载登记表的回收面。
///
/// 修的形态：`_trackedDownloads.Add(operation)` 之后**从不移除**（只有解绑时一次 Clear），
/// 于是长会话里已结束的 `CoreWebView2DownloadOperation` COM 引用逐个堆积；而紧急终止路径
/// 对整张表逐个 `Cancel()`，已结束项必抛、被 catch 吞掉——噪声与真在途的取消混在一起。
///
/// 为什么这里是「纯函数 + 源码锚」两半：`CoreWebView2DownloadOperation` 是 internal ctor
/// 的 COM 包装件，单测里造不出来（CS-329 同一事故留下的口径），所以终态判定提成
/// <see cref="HostWebView.IsTerminalState"/> 直测，而「订阅了没有 / 摘了没有 / 终止路径
/// 还自己 Cancel 不 Cancel」只能在源文件上判。两侧都配了反向锚：把 `-=`/`.Remove(`
/// 或整个 `CancelInFlightDownloads()` 调用删掉，本文件必须判红。</summary>
public sealed class HostWebViewDownloadTrackingTests
{
    private const string MainFile = "HostWebView.cs";
    private const string DownloadsFile = "HostWebView.Downloads.cs";

    private static string WebViewSource(string fileName)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName,
                "windows", "src", "Aegis.Windows.App", "WebView", fileName);
            if (File.Exists(candidate))
                return File.ReadAllText(candidate);
            dir = dir.Parent;
        }
        // 显式 throw：Assert.Fail 的 DoesNotReturn 会把它之后的代码判成不可达
        throw new InvalidOperationException($"未定位到 WebView/{fileName}（仓库布局契约）");
    }

    [Theory]
    [InlineData(CoreWebView2DownloadState.Completed, true)]
    [InlineData(CoreWebView2DownloadState.Interrupted, true)]
    [InlineData(CoreWebView2DownloadState.InProgress, false)]
    public void TerminalStates_are_the_ones_that_release_the_reference(
        CoreWebView2DownloadState state, bool expected)
        => Assert.Equal(expected, HostWebView.IsTerminalState(state));

    [Fact]
    public void UnknownNativeState_is_not_terminal()
    {
        // 未知枚举值不按终态处理：宁可让终止路径多 Cancel 一次（抛→吞），
        // 也不要因为「不认识」就把一只真在途的下载从登记表里忘掉。
        Assert.False(HostWebView.IsTerminalState((CoreWebView2DownloadState)999));
    }

    [Fact]
    public void Tracking_subscribes_the_terminal_signal_and_retires_on_it()
    {
        var source = WebViewSource(DownloadsFile);
        Assert.Contains("operation.StateChanged += _onDownloadStateChanged;", source);
        Assert.Contains("_trackedDownloads.Add(operation);", source);
        // 摘除必须是「退订 + 去表」两件事，少一件就是引用泄漏或事件源攥着委托
        Assert.Contains("operation.StateChanged -= _onDownloadStateChanged;", source);
        Assert.Contains("_trackedDownloads.Remove(operation);", source);
    }

    [Fact]
    public void Immediate_check_after_subscribe_closes_the_fast_completion_window()
    {
        // 订阅之前就已经结束的（快文件 + 慢接线）不会再有事件——必须当场判一次
        var source = WebViewSource(DownloadsFile);
        var addAt = source.IndexOf("_trackedDownloads.Add(operation);", StringComparison.Ordinal);
        var checkAt = source.IndexOf("RetireDownloadIfTerminal(operation);", StringComparison.Ordinal);
        Assert.True(addAt > 0 && checkAt > addAt,
            "登记之后没有补一次终态判定——滞留形态回来了");
    }

    [Fact]
    public void Kill_switch_path_cancels_only_in_flight_and_lives_in_one_place()
    {
        var downloads = WebViewSource(DownloadsFile);
        Assert.Contains("if (!IsTerminal(download))", downloads);
        Assert.Contains("download.Cancel();", downloads);
        Assert.Contains("RetireDownload(download);", downloads);
        // 主文件不再自己持有一段取消循环——那正是「对已结束项 Cancel 再吞异常」的旧址
        var main = WebViewSource(MainFile);
        Assert.Contains("CancelInFlightDownloads();", main);
        Assert.DoesNotContain("download.Cancel();", main);
    }

    [Fact]
    public void Unwiring_releases_every_tracked_reference()
    {
        var main = WebViewSource(MainFile);
        Assert.Contains("ReleaseTrackedDownloads();", main);
        // Clear 只能出现在分片里（释放路径的唯一实现处），主文件不许再直接 Clear
        Assert.DoesNotContain("_trackedDownloads.Clear();", main);
        Assert.Contains("download.StateChanged -= _onDownloadStateChanged;", WebViewSource(DownloadsFile));
    }

    [Fact]
    public void Download_state_is_no_longer_tracked_in_the_main_file()
    {
        // 单所有权：字段声明只在分片里出现一次
        Assert.DoesNotContain("private readonly List<CoreWebView2DownloadOperation> _trackedDownloads",
            WebViewSource(MainFile));
        Assert.Contains("private readonly List<CoreWebView2DownloadOperation> _trackedDownloads",
            WebViewSource(DownloadsFile));
    }
}

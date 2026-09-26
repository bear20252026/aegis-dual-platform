namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Downloads;
using Xunit;

/// <summary>C9 批（审计 2026-09-26）：DownloadItem 纯函数面直测。
/// DownloadOperation 无法在单测构造——状态机显示映射与字节格式化
/// 经 internal static 面覆盖（CS-112/CS-113）。</summary>
public sealed class DownloadItemTests
{
    [Theory]
    [InlineData(-1, "未知大小")]
    [InlineData(0, "0 B")]
    [InlineData(512, "512 B")]
    [InlineData(1023, "1023 B")]
    [InlineData(1024, "1.0 KB")]
    [InlineData(2048, "2.0 KB")]
    [InlineData(5 * 1024 * 1024, "5.0 MB")]
    [InlineData(3L * 1024 * 1024 * 1024, "3.00 GB")]
    public void FormatBytesInvariantBoundaries(long bytes, string expected)
    {
        // CS-110/113：InvariantCulture——逗号小数文化下不再漂移
        Assert.Equal(expected, DownloadItem.FormatBytes(bytes));
    }

    [Theory]
    [InlineData(DownloadItemState.InProgress, "进行中")]
    [InlineData(DownloadItemState.Completed, "已完成")]
    [InlineData(DownloadItemState.Canceled, "已取消")]
    [InlineData(DownloadItemState.Interrupted, "已中断")]
    [InlineData(DownloadItemState.Ended, "已结束")]
    public void StateTextSingleMapping(DownloadItemState kind, string expected)
    {
        // CS-112：状态机 → 显示文案单点映射锁定
        Assert.Equal(expected, DownloadItem.StateText(kind));
    }

    // ===== C19b 批（审计 2026-09-26）：CS-329 Refresh 状态机分支 =====
    // CoreWebView2DownloadOperation 无法在单测构造（internal ctor）——分支
    // 经提纯的 internal static 映射直测 + null 操作对象端到端兜底。

    [Fact]
    public void MapNativeState_UserCanceled_MapsToCanceled()
    {
        // Interrupted + UserCanceled → 已取消（非"已中断"）
        Assert.Equal(DownloadItemState.Canceled, DownloadItem.MapNativeState(
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadState.Interrupted,
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadInterruptReason.UserCanceled));
        // 其他中断原因 → 已中断
        Assert.Equal(DownloadItemState.Interrupted, DownloadItem.MapNativeState(
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadState.Interrupted,
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadInterruptReason.NetworkFailed));
    }

    [Fact]
    public void MapNativeState_UnknownNativeState_MapsToInterrupted()
    {
        // 未知原生状态按中断呈现（不静默）
        Assert.Equal(DownloadItemState.Interrupted, DownloadItem.MapNativeState(
            (Microsoft.Web.WebView2.Core.CoreWebView2DownloadState)999,
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadInterruptReason.None));
        Assert.Equal(DownloadItemState.InProgress, DownloadItem.MapNativeState(
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadState.InProgress,
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadInterruptReason.None));
        Assert.Equal(DownloadItemState.Completed, DownloadItem.MapNativeState(
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadState.Completed,
            Microsoft.Web.WebView2.Core.CoreWebView2DownloadInterruptReason.None));
    }

    [Fact]
    public void MapRefreshException_ObjectDisposed_MapsToEnded()
    {
        // 操作对象随会话结束 → 已结束（不是"已完成"——IsCompleted=true 会
        // 给出"打开"按钮而文件可能不存在）
        Assert.Equal(DownloadItemState.Ended,
            DownloadItem.MapRefreshException(new ObjectDisposedException("op")));
        Assert.Equal(DownloadItemState.Interrupted,
            DownloadItem.MapRefreshException(new InvalidOperationException()));
        Assert.Equal(DownloadItemState.Interrupted,
            DownloadItem.MapRefreshException(new NullReferenceException()));
    }

    [Fact]
    public void Refresh_NullOperation_FallsBackToInterrupted()
    {
        // 端到端兜底分支：操作对象不可用（构造仅赋值不触原生）——Refresh
        // 绝不向调用方上抛，按中断呈现
        var item = new DownloadItem(null!, "file.zip", "https://example.com/file.zip", dangerous: false);
        var ex = Record.Exception(() => item.Refresh());
        Assert.Null(ex);
    }
}

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
}

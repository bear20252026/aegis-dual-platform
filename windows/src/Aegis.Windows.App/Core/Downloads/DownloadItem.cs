namespace Aegis.Windows.Core.Downloads;

using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using Microsoft.Web.WebView2.Core;

/// <summary>下载条目视图模型（M4 下载管理面板——ADR-009 D2 领域层：
/// INPC 数据 + DownloadOperation 引用；进度经面板定时器轮询原生
/// Progress API，与 Python「pywebview 天花板不支持下载 UI」形成对照）。
/// 安全边界：本类只读呈现，暂停/恢复/取消直接调用原生 DownloadOperation
/// ——不经任何远程页面可触达的通道。</summary>
public sealed class DownloadItem : INotifyPropertyChanged
{
    private string _state = "进行中";
    private long _receivedBytes;
    private long _totalBytes;
    private DateTime? _completedAt;

    public DownloadItem(CoreWebView2DownloadOperation operation, string fileName, string url, bool dangerous)
    {
        Operation = operation;
        FileName = string.IsNullOrWhiteSpace(fileName) ? "未命名下载" : fileName;
        Url = url;
        Dangerous = dangerous;
    }

    /// <summary>已完成文件的完整路径（打开文件/打开文件夹用）。</summary>
    public string FilePath => Operation?.ResultFilePath ?? string.Empty;

    /// <summary>下载是否已完成（供 UI 显示"打开"按钮）。</summary>
    public bool IsCompleted => State == "已完成";

    /// <summary>完成时刻（用于持久化记录）。</summary>
    public DateTime? CompletedAt => _completedAt;

    public string FileSizeText => TotalBytes > 0 ? FormatBytes(TotalBytes) : "未知大小";

    public event PropertyChangedEventHandler? PropertyChanged;

    public CoreWebView2DownloadOperation Operation { get; }

    public string FileName { get; }

    public string Url { get; }

    /// <summary>危险扩展下载（经用户显式确认后放行——审计链保留）。</summary>
    public bool Dangerous { get; }

    public string State { get => _state; private set => SetField(ref _state, value); }

    public long ReceivedBytes { get => _receivedBytes; private set => SetField(ref _receivedBytes, value); }

    public long TotalBytes { get => _totalBytes; private set => SetField(ref _totalBytes, value); }

    /// <summary>进度百分比（总大小未知时按 0 呈现——不定长下载无虚假进度）。</summary>
    public double Percent => TotalBytes > 0 ? Math.Min(100.0, ReceivedBytes * 100.0 / TotalBytes) : 0;

    /// <summary>摘要行（大小 + 来源主机——面板可见性，不静默）。</summary>
    public string Summary
    {
        get
        {
            var host = Uri.TryCreate(Url, UriKind.Absolute, out var uri) ? uri.Host : Url;
            return $"{FormatBytes(ReceivedBytes)} / {FormatBytes(TotalBytes)} · {host}{(Dangerous ? " · 危险扩展（已确认）" : string.Empty)}";
        }
    }

    private static string FormatBytes(long bytes) =>
        bytes < 0
            ? "未知大小"
            : bytes < 1024 ? $"{bytes} B"
            : bytes < 1024 * 1024 ? $"{bytes / 1024.0:F1} KB"
            : bytes < 1024L * 1024 * 1024 ? $"{bytes / (1024.0 * 1024):F1} MB"
            : $"{bytes / (1024.0 * 1024 * 1024):F2} GB";

    /// <summary>刷新原生进度（面板 DispatcherTimer 周期调用——属性直读，
    /// 兼容 SDK 1.0.2903.40 的扁平 Progress API）。状态映射：InProgress/
    /// Completed/Interrupted（含 UserCanceled→已取消）——绝不静默。</summary>
    public void Refresh()
    {
        try
        {
            ReceivedBytes = (long)Operation.BytesReceived;
            TotalBytes = (long)(Operation.TotalBytesToReceive ?? 0UL);
            State = Operation.State switch
            {
                CoreWebView2DownloadState.InProgress => "进行中",
                CoreWebView2DownloadState.Completed => "已完成",
                CoreWebView2DownloadState.Interrupted when Operation.InterruptReason
                    == CoreWebView2DownloadInterruptReason.UserCanceled => "已取消",
                CoreWebView2DownloadState.Interrupted => "已中断",
                _ => Operation.State.ToString(),
            };
        }
        catch (ObjectDisposedException)
        {
            State = "已完成";  // 操作对象随浏览器会话结束——按完成处理
        }
        catch (InvalidOperationException)
        {
            State = "已中断";
        }
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Percent)));
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Summary)));
    }

    public void Pause()
    {
        try
        {
            Operation.Pause();
        }
        catch (Exception)
        {
            // 不可暂停或已结束——状态由 Refresh 呈现
        }
        Refresh();
    }

    public void Resume()
    {
        try
        {
            if (Operation.CanResume)
                Operation.Resume();
        }
        catch (Exception)
        {
            // 不可恢复——状态由 Refresh 呈现
        }
        Refresh();
    }

    public void Cancel()
    {
        try
        {
            Operation.Cancel();
        }
        catch (Exception)
        {
            // 已结束——状态由 Refresh 呈现
        }
        Refresh();
    }

    private void SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (Equals(field, value))
            return;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}

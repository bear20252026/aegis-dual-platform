namespace Aegis.Windows.Core.Downloads;

using System;
using System.ComponentModel;
using System.Globalization;
using System.Runtime.CompilerServices;
using Microsoft.Web.WebView2.Core;

/// <summary>下载条目视图模型（M4 下载管理面板——ADR-009 D2 领域层：
/// INPC 数据 + DownloadOperation 引用；进度经面板定时器轮询原生
/// Progress API，与 Python「pywebview 天花板不支持下载 UI」形成对照）。
/// 安全边界：本类只读呈现，暂停/恢复/取消直接调用原生 DownloadOperation
/// ——不经任何远程页面可触达的通道。</summary>
public sealed class DownloadItem : INotifyPropertyChanged
{
    // CS-112：状态机枚举单源——此前中文串既当存储又当显示，IsCompleted 等
    // 比较依赖字面量，切换点拼写漂移即静默失配；显示文案经 StateText 单点映射。
    private DownloadItemState _stateKind = DownloadItemState.InProgress;
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
    public bool IsCompleted => _stateKind == DownloadItemState.Completed;

    /// <summary>完成时刻（用于持久化记录）。</summary>
    public DateTime? CompletedAt => _completedAt;

    public string FileSizeText => TotalBytes > 0 ? FormatBytes(TotalBytes) : "未知大小";

    public event PropertyChangedEventHandler? PropertyChanged;

    public CoreWebView2DownloadOperation Operation { get; }

    public string FileName { get; }

    public string Url { get; }

    /// <summary>危险扩展下载（经用户显式确认后放行——审计链保留）。</summary>
    public bool Dangerous { get; }

    /// <summary>状态显示文案（绑定点——由 StateKind 单点派生）。</summary>
    public string State => StateText(_stateKind);

    /// <summary>类型化状态（CS-112——测试与内部比较不再解析中文字面量）。</summary>
    internal DownloadItemState StateKind => _stateKind;

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

    /// <summary>CS-113：字节量格式化提 internal 直测；CS-110：InvariantCulture
    /// ——默认文化小数点/分组符漂移（逗号文化显示 "1,5 MB"）。</summary>
    internal static string FormatBytes(long bytes) =>
        bytes < 0
            ? "未知大小"
            : bytes < 1024 ? $"{bytes.ToString(CultureInfo.InvariantCulture)} B"
            : bytes < 1024 * 1024 ? $"{(bytes / 1024.0).ToString("F1", CultureInfo.InvariantCulture)} KB"
            : bytes < 1024L * 1024 * 1024 ? $"{(bytes / (1024.0 * 1024)).ToString("F1", CultureInfo.InvariantCulture)} MB"
            : $"{(bytes / (1024.0 * 1024 * 1024)).ToString("F2", CultureInfo.InvariantCulture)} GB";

    /// <summary>状态机 → 显示文案单一映射（CS-112）。</summary>
    internal static string StateText(DownloadItemState kind) => kind switch
    {
        DownloadItemState.InProgress => "进行中",
        DownloadItemState.Completed => "已完成",
        DownloadItemState.Canceled => "已取消",
        DownloadItemState.Interrupted => "已中断",
        DownloadItemState.Ended => "已结束",
        _ => kind.ToString(),
    };

    /// <summary>刷新原生进度（面板 DispatcherTimer 周期调用——属性直读，
    /// 兼容 SDK 1.0.2903.40 的扁平 Progress API）。状态映射：InProgress/
    /// Completed/Interrupted（含 UserCanceled→已取消）——绝不静默。
    /// 派生属性（Percent/Summary）只在字节变化时通知——此前每 tick 无条件
    /// 强发两个 PropertyChanged，挂窗期间持续触发绑定重算。</summary>
    public void Refresh()
    {
        long beforeReceived = _receivedBytes, beforeTotal = _totalBytes;
        try
        {
            ReceivedBytes = (long)Operation.BytesReceived;
            TotalBytes = (long)(Operation.TotalBytesToReceive ?? 0UL);
            var kind = Operation.State switch
            {
                CoreWebView2DownloadState.InProgress => DownloadItemState.InProgress,
                CoreWebView2DownloadState.Completed => DownloadItemState.Completed,
                CoreWebView2DownloadState.Interrupted when Operation.InterruptReason
                    == CoreWebView2DownloadInterruptReason.UserCanceled => DownloadItemState.Canceled,
                CoreWebView2DownloadState.Interrupted => DownloadItemState.Interrupted,
                _ => DownloadItemState.Interrupted,  // 未知原生状态按中断呈现（不静默）
            };
            if (kind == DownloadItemState.Completed && _completedAt is null)
                _completedAt = DateTime.Now;
            SetState(kind);
        }
        catch (ObjectDisposedException)
        {
            // 操作对象随浏览器会话结束——如实标记「已结束」（此前标「已完成」，
            // IsCompleted=true 会给出"打开"按钮而文件可能并不存在）
            SetState(DownloadItemState.Ended);
        }
        catch (InvalidOperationException)
        {
            SetState(DownloadItemState.Interrupted);
        }
        catch (Exception)
        {
            // CS-111：其余异常面兜底（SDK 回调竞态等）——轮询路径绝不向
            // UI 定时器上抛
            SetState(DownloadItemState.Interrupted);
        }
        if (beforeReceived != _receivedBytes || beforeTotal != _totalBytes)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Percent)));
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Summary)));
        }
    }

    private void SetState(DownloadItemState kind)
    {
        if (_stateKind == kind)
            return;
        _stateKind = kind;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(State)));
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsCompleted)));
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

/// <summary>下载条目状态机（CS-112）——存储/比较用类型化枚举，显示经
/// DownloadItem.StateText 单点映射。</summary>
public enum DownloadItemState
{
    InProgress,
    Completed,
    Canceled,
    Interrupted,
    Ended,
}

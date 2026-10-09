namespace Aegis.Windows.Chrome;

using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;
using System.Windows.Controls;

/// <summary>适配单个 TabRuntime 的初始化、延迟导航和关闭生命周期。</summary>
public sealed class TabRuntimeLifetime : IDisposable
{
    private readonly CancellationTokenSource _cancellation = new();
    // 构造期缓存令牌：Close 后 CTS.Dispose，迟到的延迟导航回调仍可安全读
    // CancellationToken（直接访问 _cancellation.Token 会抛 ObjectDisposedException）
    private readonly CancellationToken _token;
    private bool _disposed;

    public TabRuntimeLifetime(TabRuntime runtime)
    {
        Runtime = runtime ?? throw new ArgumentNullException(nameof(runtime));
        Generation = Guid.NewGuid();
        _token = _cancellation.Token;
    }

    public TabRuntime Runtime { get; }
    public Guid Generation { get; }
    public CancellationToken CancellationToken => _token;
    public bool IsDisposed => _disposed;

    /// <summary>内部观察 fire-and-forget 初始化异常，避免未观察任务异常。</summary>
    public void InitializeAsync(Action<Exception>? onError = null)
    {
        _ = ObserveInitializationAsync(onError);
    }

    /// <summary>R8-CS-SEC-07（第八轮 2026-10-08）：document-ready 接线段失败闭合的审计码。</summary>
    internal const string CoreReadyErrorCode = "core_ready_error";

    /// <summary>R8-CS-SEC-07：拆除动作自己也失败时的审计码（见下「残余」）。</summary>
    internal const string CoreReadyTeardownErrorCode = "core_ready_teardown_failed";

    /// <summary>
    /// document-ready 接线段的失败闭合核（纯函数，无 COM——与
    /// `HostWebView.IsAuthorizedFailClosed`、`SubresourceDenialFailClosed` 同一族口径）。
    ///
    /// 存在的理由：`InitializeAsync` 只观察 `Runtime.InitAsync()` 的异常，而
    /// `CoreWebView2InitializationCompleted` **回调体**里的抛出（虚拟主机映射、
    /// `OnCoreReady` 内含的 broker `RegisterSession`（会话池 1024 满即抛）、首次导航、
    /// NTP 桥绑定）此前没有任何观察方——它一路冒到 Dispatcher 的全局未处理异常弹窗
    /// （30s 频控后静默），现场留下的是「一个能显示、却没接上策略处理器的标签」。
    /// 现在：抛出 ⇒ 结构化留痕 ⇒ 拆除该标签，不留半接线状态。
    ///
    /// 残余（如实记，不假装拦住）：拆除动作自己再失败时只补第二条留痕、**不重抛**——
    /// 重抛等于把这条路径送回它正要消除的全局弹窗；此时半接线标签可能存活，但它的
    /// 每次导航仍要过 broker 授权，而授权求值本身失败闭合（R8-CS-SEC-02）。
    /// </summary>
    internal static void RunCoreReadyFailClosed(
        Action wire, Func<string> tabIdForLog, Action teardown)
    {
        try
        {
            wire();
        }
        catch (Exception ex)
        {
            Core.Security.SecurityLog.Write(
                $"[tab] document-ready 接线异常——按失败闭合拆除标签: "
                + $"{ex.GetType().Name}: {ex.Message} tab={Safe(tabIdForLog)} "
                + $"code={CoreReadyErrorCode}");
            try
            {
                teardown();
            }
            catch (Exception teardownEx)
            {
                Core.Security.SecurityLog.Write(
                    $"[tab] 失败闭合的拆除动作自己也抛出——标签可能仍在但未接线: "
                    + $"{teardownEx.GetType().Name}: {teardownEx.Message} "
                    + $"tab={Safe(tabIdForLog)} code={CoreReadyTeardownErrorCode}");
            }
        }
    }

    /// <summary>取日志用的标签 id：连取 id 都可能抛（控件已退休），失败给占位符。</summary>
    private static string Safe(Func<string> reader)
    {
        try
        {
            return reader();
        }
        catch (Exception ex)
        {
            return $"<unavailable:{ex.GetType().Name}>";
        }
    }

    private async Task ObserveInitializationAsync(Action<Exception>? onError)
    {
        try
        {
            await Runtime.InitAsync().ConfigureAwait(true);
        }
        catch (OperationCanceledException) when (_cancellation.IsCancellationRequested) { }
        catch (Exception ex)
        {
            onError?.Invoke(ex);
        }
    }

    /// <summary>调用方应先将控件从视觉树摘除，再调用此方法。</summary>
    public void Close()
    {
        if (_disposed)
            return;
        _disposed = true;
        _cancellation.Cancel();
        Runtime.Dispose();
        _cancellation.Dispose();
    }

    public void Dispose() => Close();
}

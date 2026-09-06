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
    private bool _disposed;

    public TabRuntimeLifetime(TabRuntime runtime)
    {
        Runtime = runtime ?? throw new ArgumentNullException(nameof(runtime));
        Generation = Guid.NewGuid();
    }

    public TabRuntime Runtime { get; }
    public Guid Generation { get; }
    public CancellationToken CancellationToken => _cancellation.Token;
    public bool IsDisposed => _disposed;

    /// <summary>内部观察 fire-and-forget 初始化异常，避免未观察任务异常。</summary>
    public void InitializeAsync(Action<Exception>? onError = null)
    {
        _ = ObserveInitializationAsync(onError);
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

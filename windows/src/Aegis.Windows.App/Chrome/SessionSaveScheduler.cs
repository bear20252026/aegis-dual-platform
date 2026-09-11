namespace Aegis.Windows.Chrome;

using System;

/// <summary>防抖计时器抽象（生产用 WPF DispatcherTimer；单测用可控假实现——
/// 防抖时序不需要真实等待）。</summary>
public interface IDebounceTimer : IDisposable
{
    /// <summary>计时到期触发（DispatcherTimer 的 Tick）。</summary>
    event EventHandler Elapsed;

    /// <summary>启动/重启一次防抖窗口。</summary>
    void Restart(TimeSpan interval);

    /// <summary>取消未到期的计时。</summary>
    void Stop();
}

/// <summary>DispatcherTimer 适配（UI 线程计时——与此前内联实现等价）。</summary>
public sealed class DispatcherDebounceTimer : IDebounceTimer
{
    private readonly System.Windows.Threading.DispatcherTimer _timer = new();

    public event EventHandler? Elapsed;

    public DispatcherDebounceTimer() => _timer.Tick += (s, e) => Elapsed?.Invoke(s, e);

    public void Restart(TimeSpan interval)
    {
        _timer.Interval = interval;
        _timer.Stop();
        _timer.Start();
    }

    public void Stop() => _timer.Stop();

    public void Dispose() => _timer.Stop();
}

/// <summary>会话落盘防抖调度器（上帝对象拆分·第四批）：标脏只重启 2s 计时，
/// 到期一次落盘；Flush 立即落盘兜底（关闭/退出）；恢复会话期间（BeginRestore
/// 返回的抑制域内）标脏与刷盘全部跳过——关闭旧标签触发的落盘不会覆盖即将
/// 恢复的快照。纯逻辑可单测（timer 注入）。</summary>
public sealed class SessionSaveScheduler
{
    private readonly IDebounceTimer _timer;
    private readonly Action _save;
    private readonly TimeSpan _debounce;
    private bool _restoring;

    public SessionSaveScheduler(IDebounceTimer timer, Action save, TimeSpan debounce)
    {
        _timer = timer;
        _save = save;
        _debounce = debounce;
        _timer.Elapsed += (_, _) =>
        {
            _timer.Stop();
            _save();
        };
    }

    /// <summary>标脏：重启防抖窗口（此前每次 NavigationCompleted 同步写
    /// SQLite 的写放大治理入口）。恢复抑制域内忽略。</summary>
    public void MarkDirty()
    {
        if (_restoring)
            return;
        _timer.Restart(_debounce);
    }

    /// <summary>立即落盘（窗口关闭/正常退出——防抖未到期的脏数据不丢）。
    /// 恢复抑制域内跳过。</summary>
    public void Flush()
    {
        _timer.Stop();
        if (!_restoring)
            _save();
    }

    /// <summary>进入恢复抑制域：域内 MarkDirty/Flush 均不落盘；Dispose 恢复。
    /// 可重入安全（内层先退出不清除外层抑制）。</summary>
    public IDisposable BeginRestore()
    {
        _restoring = true;
        return new RestoreScope(this);
    }

    private sealed class RestoreScope(SessionSaveScheduler owner) : IDisposable
    {
        private bool _disposed;

        public void Dispose()
        {
            if (_disposed)
                return;
            _disposed = true;
            owner._restoring = false;
        }
    }
}

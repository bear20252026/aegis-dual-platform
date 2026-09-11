namespace Aegis.Windows.Core.Tests;

using System;
using Aegis.Windows.Chrome;
using Xunit;

/// <summary>会话落盘防抖调度器单测（上帝对象拆分·第四批）——标脏只重启计时、
/// 到期一次落盘、Flush 立即落盘且停表、恢复抑制域内全跳过。</summary>
public class SessionSaveSchedulerTests
{
    private sealed class ManualTimer : IDebounceTimer
    {
        public event EventHandler? Elapsed;
        public TimeSpan? LastInterval;
        public bool IsRunning;

        public void Restart(TimeSpan interval)
        {
            LastInterval = interval;
            IsRunning = true;
        }

        public void Stop() => IsRunning = false;

        /// <summary>模拟防抖到期（仅当计时进行中才触发）。</summary>
        public void Fire()
        {
            if (!IsRunning)
                return;
            IsRunning = false;
            Elapsed?.Invoke(this, EventArgs.Empty);
        }

        public void Dispose() { }
    }

    private sealed class Harness
    {
        public readonly ManualTimer Timer = new();
        public readonly SessionSaveScheduler Scheduler;
        public int Saves;

        public Harness()
        {
            Scheduler = new SessionSaveScheduler(
                Timer, () => Saves++, TimeSpan.FromMilliseconds(2000));
        }
    }

    [Fact]
    public void MarkDirty_RestartsDebounceWindow_WithoutSaving()
    {
        var h = new Harness();
        h.Scheduler.MarkDirty();
        h.Scheduler.MarkDirty();
        Assert.True(h.Timer.IsRunning);
        Assert.Equal(TimeSpan.FromMilliseconds(2000), h.Timer.LastInterval);
        Assert.Equal(0, h.Saves);
    }

    [Fact]
    public void Elapsed_SavesOnce_AndStopsTimer()
    {
        var h = new Harness();
        h.Scheduler.MarkDirty();
        h.Timer.Fire();
        Assert.Equal(1, h.Saves);
        Assert.False(h.Timer.IsRunning);
        // 计时器已停：再模拟到期不重复落盘
        h.Timer.Fire();
        Assert.Equal(1, h.Saves);
    }

    [Fact]
    public void Flush_SavesImmediately_AndCancelsPendingDebounce()
    {
        var h = new Harness();
        h.Scheduler.MarkDirty();
        h.Scheduler.Flush();
        Assert.Equal(1, h.Saves);
        Assert.False(h.Timer.IsRunning);
        // 防抖已取消：残留的到期事件不再落盘
        h.Timer.Fire();
        Assert.Equal(1, h.Saves);
    }

    [Fact]
    public void RestoreScope_SuppressesBothMarkDirtyAndFlush()
    {
        var h = new Harness();
        using (h.Scheduler.BeginRestore())
        {
            h.Scheduler.MarkDirty();
            Assert.False(h.Timer.IsRunning);
            h.Scheduler.Flush();
            Assert.Equal(0, h.Saves);
        }
        // 退出抑制域后恢复正常落盘
        h.Scheduler.Flush();
        Assert.Equal(1, h.Saves);
    }

    [Fact]
    public void RestoreScope_DoubleDispose_IsSafe()
    {
        var h = new Harness();
        var scope = h.Scheduler.BeginRestore();
        scope.Dispose();
        scope.Dispose();
        h.Scheduler.Flush();
        Assert.Equal(1, h.Saves);
    }
}

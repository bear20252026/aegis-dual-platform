namespace Aegis.Windows;

using System;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;
using Aegis.Windows.Core.Security;
public partial class App : Application
{
    // 弹窗频控：持续性异常（如每帧渲染错误）此前会造成无限 MessageBox 循环，
    // 应用既无法操作也无法退出——30 秒窗口内最多弹 3 次，超出只记日志
    private static readonly long[] PopupTicks = new long[3];

    public App()
    {
        // 应用级未处理异常兜底：记录到安全日志 + 友好提示，阻止「闪退」。
        // 个别 UI 事件抛异常的根因由此可定位（日志含类型/消息），而非静默崩溃。
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        // 后台线程/fire-and-forget 异常同样留痕（此前直接杀进程且无日志）
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            TryLog($"[fatal] 后台线程未处理异常: {e.ExceptionObject}");
        };
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            TryLog($"[fatal] 未观察任务异常: {e.Exception}");
            e.SetObserved();  // 不因未观察任务异常终止进程
        };
    }

    private static void OnDispatcherUnhandledException(object? sender, DispatcherUnhandledExceptionEventArgs e)
    {
        TryLog(
            $"[fatal] 未处理异常（已拦截，应用继续运行）: {e.Exception?.GetType().Name}: {e.Exception?.Message}{Environment.NewLine}{e.Exception}");
        if (ShouldShowPopup())
        {
            MessageBox.Show(
                $"发生未处理的异常，应用已阻止崩溃并继续运行。\n\n" +
                $"{e.Exception?.GetType().Name}: {e.Exception?.Message}",
                "Aegis",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        e.Handled = true;  // 已处理——应用不退出（频控超限时静默吞掉并持续记日志）
    }

    private static bool ShouldShowPopup()
    {
        var now = Environment.TickCount64;
        lock (PopupTicks)
        {
            foreach (var tick in PopupTicks)
            {
                if (now - tick >= 30_000)
                {
                    PopupTicks[Array.IndexOf(PopupTicks, tick)] = now;
                    return true;
                }
            }
            return false;  // 30s 内已弹 3 次——静默
        }
    }

    private static void TryLog(string message)
    {
        try
        {
            SecurityLog.Write(message);
        }
        catch
        {
            // 日志不可写时不阻断处理
        }
    }

    /// <summary>组合根：装配存储/策略/broker 后构造主窗口。MainWindow 不再自建
    /// 依赖（此前的字段初始器）——依赖显式可注入、可换内存实现、可构造测。</summary>
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var window = new Chrome.MainWindow(Chrome.MainWindowDependencies.Defaults());
        MainWindow = window;
        window.Show();
    }
}

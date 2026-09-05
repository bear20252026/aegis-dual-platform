namespace Aegis.Windows;

using System;
using System.Windows;
using System.Windows.Threading;
using Aegis.Windows.Core.Security;

public partial class App : Application
{
    public App()
    {
        // 应用级未处理异常兜底：记录到安全日志 + 友好提示，阻止「闪退」。
        // 个别 UI 事件抛异常的根因由此可定位（日志含类型/消息），而非静默崩溃。
        DispatcherUnhandledException += OnDispatcherUnhandledException;
    }

    private static void OnDispatcherUnhandledException(object? sender, DispatcherUnhandledExceptionEventArgs e)
    {
        try
        {
            SecurityLog.Write(
                $"[fatal] 未处理异常（已拦截，应用继续运行）: {e.Exception?.GetType().Name}: {e.Exception?.Message}{Environment.NewLine}{e.Exception}");
        }
        catch
        {
            // 日志不可写时不阻断处理
        }
        MessageBox.Show(
            $"发生未处理的异常，应用已阻止崩溃并继续运行。\n\n" +
            $"{e.Exception?.GetType().Name}: {e.Exception?.Message}",
            "Aegis",
            MessageBoxButton.OK,
            MessageBoxImage.Error);
        e.Handled = true;  // 已处理——应用不退出
    }
}
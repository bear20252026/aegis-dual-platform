namespace Aegis.Windows;

using System;
using System.Windows;

/// <summary>阶段 C 入口（蓝图 windows/src/——Aegis.Windows.App——组合启动）。
/// 非提权进程（WebView2 官方安全最佳实践——host 组件保持最低权限）。
/// 目标：远程页面无 native bridge——所有安全事件经 Aegis.Windows.Broker。</summary>
public static class Program
{
    [STAThread]
    public static void Main()
    {
        // App.xaml 现为无 StartupUri/无资源的组合根占位（窗口由 App.OnStartup
        // 以注入依赖构造），PresentationBuildTasks 对空 Application XAML 不再
        // 生成 InitializeComponent——无需加载的 XAML 资源，跳过调用。
        var app = new App();
        app.Run();
    }
}

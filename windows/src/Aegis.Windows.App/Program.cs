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
        var app = new App();
        app.InitializeComponent();
        app.Run();
    }
}

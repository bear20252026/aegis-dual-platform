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
        // App.xaml 自 UI 现代化批①（33edbaa）起携带全局合并资源字典
        // （ChromeStyles——图标字体/深色 ComboBox/细滚动条），必须经
        // InitializeComponent 加载进 Application.Resources——跳过调用会使
        // MainWindow 的 StaticResource 全部 XamlParseException（2026-09-28
        // 三次启动 [fatal] 的根因：旧注释「无资源可跳过」已失实）。
        var app = new App();
        app.InitializeComponent();
        app.Run();
    }
}

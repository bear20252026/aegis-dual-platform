namespace Aegis.Host;

using System;
using System.Windows;

/// <summary>重构第 1 阶段入口（专家最终路线）：C#/.NET 10 + 原生 WebView2。
/// 非提权进程（标准用户完整性——WebView2 官方安全最佳实践）。
/// 目标：远程页面无 native bridge——所有安全事件经 BrowserPolicyBroker。</summary>
public static class Program
{
    [STAThread]
    public static void Main()
    {
        // 非提权运行（WebView2 官方建议——host 组件保持最低权限）
        var app = new App();
        app.InitializeComponent();
        app.Run();
    }
}

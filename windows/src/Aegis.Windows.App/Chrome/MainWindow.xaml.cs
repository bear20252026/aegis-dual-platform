namespace Aegis.Windows.Chrome;

using System;
using System.Windows;
using System.Windows.Input;
using Aegis.Windows.Broker;
using Microsoft.Web.WebView2.Core;

/// <summary>主窗口（受信 chrome UI 域——蓝图阶段 C）。
/// Chrome 只提交用户意图和显示结果——不能绕过 Broker（ADR-002）。
/// 远程页面无 native bridge——WebView2 全部安全事件经 Broker（ADR-003）。</summary>
public partial class MainWindow : Window
{
    private readonly BrowserPolicyBroker _broker = new();
    private readonly WebView.HostWebView _host;
    private readonly string _sessionId = Guid.NewGuid().ToString("N");

    public MainWindow()
    {
        InitializeComponent();
        _host = new WebView.HostWebView(_broker, _sessionId);
        Browser.CoreWebView2InitializationCompleted += OnWebViewReady;
        Browser.Source = new Uri("about:blank");
    }

    private void OnWebViewReady(object? sender, CoreWebView2InitializationCompletedEventArgs e)
    {
        if (!e.IsSuccess)
            return;
        _host.WireEvents(Browser.CoreWebView2);
        // 阶段 C：导航完成——错误状态进入错误页（安全错误对用户可见——不静默）
        Browser.CoreWebView2.NavigationCompleted += (_, args) =>
        {
            if (!args.IsSuccess && args.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
            {
                ErrorPage.Text = $"导航失败：{args.WebErrorStatus}（已拒绝/无法加载）";
                ErrorPage.Visibility = Visibility.Visible;
            }
            else
            {
                ErrorPage.Visibility = Visibility.Collapsed;
            }
        };
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Uri.TryCreate(AddressBar.Text, UriKind.Absolute, out var uri))
            Browser.Source = uri;  // 导航经 NavigationStarting → Broker 决策（真实取消）
    }

    private void Back_Click(object sender, RoutedEventArgs e) => Browser.GoBack();
    private void Forward_Click(object sender, RoutedEventArgs e) => Browser.GoForward();
    private void Refresh_Click(object sender, RoutedEventArgs e) => Browser.Reload();
    private void Stop_Click(object sender, RoutedEventArgs e) => Browser.Stop();
}

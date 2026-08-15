namespace Aegis.Host;

using System;
using System.Windows;
using System.Windows.Input;
using Aegis.Host.Broker;

/// <summary>主窗口（受信 chrome UI 域——专家最终路线）。
/// 远程页面无 native bridge——WebView2 全部安全事件经 BrowserPolicyBroker。</summary>
public partial class MainWindow : Window
{
    private readonly BrowserPolicyBroker _broker = new();
    private readonly WebView.HostWebView _host;

    public MainWindow()
    {
        InitializeComponent();
        _host = new WebView.HostWebView(_broker, Guid.NewGuid().ToString("N"));
        Browser.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (e.IsSuccess)
                _host.WireEvents(Browser.CoreWebView2);
        };
        Browser.Source = new Uri("about:blank");
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Uri.TryCreate(AddressBar.Text, UriKind.Absolute, out var uri))
            Browser.Source = uri;  // 导航经 NavigationStarting → broker 决策（真实取消）
    }

    private void Back_Click(object sender, RoutedEventArgs e) => Browser.GoBack();
    private void Forward_Click(object sender, RoutedEventArgs e) => Browser.GoForward();
    private void Refresh_Click(object sender, RoutedEventArgs e) => Browser.Reload();
}

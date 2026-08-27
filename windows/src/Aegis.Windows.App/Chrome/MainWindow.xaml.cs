namespace Aegis.Windows.Chrome;

using System;
using System.ComponentModel;
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
        _host.NavigationConfirmationRequested += OnNavigationConfirmationRequested;
        _host.NavigationConfirmationResolved += OnNavigationConfirmationResolved;
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

    private void OnNavigationConfirmationRequested(
        object? sender,
        WebView.NavigationConfirmationRequestedEventArgs e)
    {
        ApprovalOrigin.Text = e.Request.Origin;
        ApprovalPath.Text = e.Request.Path;
        ApprovalScope.Text = e.Request.Scope;
        ApprovalExpiry.Text = $"此请求将在 {e.Request.ExpiresAt.ToLocalTime():yyyy-MM-dd HH:mm:ss} 过期。";
        SetNavigationControlsEnabled(false);
        ApprovalOverlay.Visibility = Visibility.Visible;
        Keyboard.Focus(ApprovalDenyButton);
    }

    private void OnNavigationConfirmationResolved(object? sender, EventArgs e)
    {
        ApprovalOverlay.Visibility = Visibility.Collapsed;
        SetNavigationControlsEnabled(true);
        ApprovalOrigin.Text = string.Empty;
        ApprovalPath.Text = string.Empty;
        ApprovalScope.Text = string.Empty;
        ApprovalExpiry.Text = string.Empty;
    }

    private void ApprovalAllow_Click(object sender, RoutedEventArgs e)
    {
        if (Browser.CoreWebView2 is null)
        {
            _host.RejectPendingNavigation();
            ErrorPage.Text = "确认请求已失效、被拒绝或无法安全恢复导航。";
            ErrorPage.Visibility = Visibility.Visible;
            return;
        }
        if (!_host.ApprovePendingNavigation(Browser.CoreWebView2))
        {
            ErrorPage.Text = "确认请求已失效、被拒绝或无法安全恢复导航。";
            ErrorPage.Visibility = Visibility.Visible;
        }
    }

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e)
    {
        _host.RejectPendingNavigation();
        ErrorPage.Text = "已拒绝该导航请求。";
        ErrorPage.Visibility = Visibility.Visible;
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (ApprovalOverlay.Visibility != Visibility.Visible || e.Key != Key.Escape)
            return;
        _host.RejectPendingNavigation();
        ErrorPage.Text = "已拒绝该导航请求。";
        ErrorPage.Visibility = Visibility.Visible;
        e.Handled = true;
    }

    private void Window_Closing(object? sender, CancelEventArgs e) => _host.RejectPendingNavigation();

    private void SetNavigationControlsEnabled(bool isEnabled)
    {
        AddressBar.IsEnabled = isEnabled;
        BackButton.IsEnabled = isEnabled;
        ForwardButton.IsEnabled = isEnabled;
        RefreshButton.IsEnabled = isEnabled;
        StopButton.IsEnabled = isEnabled;
    }

    protected override void OnClosed(EventArgs e)
    {
        Browser.CoreWebView2InitializationCompleted -= OnWebViewReady;
        _host.NavigationConfirmationRequested -= OnNavigationConfirmationRequested;
        _host.NavigationConfirmationResolved -= OnNavigationConfirmationResolved;
        _host.Dispose();
        _broker.Dispose();
        Browser.Dispose();
        base.OnClosed(e);
    }
}

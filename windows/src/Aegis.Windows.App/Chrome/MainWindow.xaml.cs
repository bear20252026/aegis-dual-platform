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
                ErrorPagePanel.Visibility = Visibility.Visible;
            }
            else
            {
                ErrorPagePanel.Visibility = Visibility.Collapsed;
            }
            // 地址栏随实际页面同步（对齐 Android P1-6——聚焦编辑时不抢）
            if (!AddressBar.IsKeyboardFocused)
                AddressBar.Text = Browser.Source?.ToString() ?? string.Empty;
        };
        // 窗口标题随页面标题变化（对齐 Android Tab.title 回填语义）
        Browser.CoreWebView2.DocumentTitleChanged += (_, _) =>
        {
            var title = Browser.CoreWebView2.DocumentTitle;
            Title = string.IsNullOrWhiteSpace(title) ? "Aegis" : $"{title} · Aegis";
        };
    }

    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e) =>
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;

    private void NavigateFromAddressBar()
    {
        // 输入归一单源（UrlNormalizer——与 Android SearchEngines.kt 跨端契约对齐）：
        // 搜索词拼引擎 URL；非导航 scheme 拒绝；最终仍经 Broker 决策。
        var target = UrlNormalizer.Normalize(AddressBar.Text);
        if (target is null)
        {
            ErrorPage.Text = "无法导航：输入为空，或属于非导航协议（file:/javascript:/data: 等已被拒绝）。";
            ErrorPagePanel.Visibility = Visibility.Visible;
            return;
        }
        Browser.Source = new Uri(target);  // 导航经 NavigationStarting → Broker 决策（真实取消）
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }

    private void Open_Click(object sender, RoutedEventArgs e) => NavigateFromAddressBar();

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
            ErrorPagePanel.Visibility = Visibility.Visible;
            return;
        }
        if (!_host.ApprovePendingNavigation(Browser.CoreWebView2))
        {
            ErrorPage.Text = "确认请求已失效、被拒绝或无法安全恢复导航。";
            ErrorPagePanel.Visibility = Visibility.Visible;
        }
    }

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e)
    {
        _host.RejectPendingNavigation();
        ErrorPage.Text = "已拒绝该导航请求。";
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // Ctrl+L 聚焦并全选地址栏（start.html 页脚提示的跨端快捷键契约）
        if (e.Key == Key.L && Keyboard.Modifiers == ModifierKeys.Control)
        {
            AddressBar.Focus();
            AddressBar.SelectAll();
            e.Handled = true;
            return;
        }
        if (ApprovalOverlay.Visibility != Visibility.Visible || e.Key != Key.Escape)
            return;
        _host.RejectPendingNavigation();
        ErrorPage.Text = "已拒绝该导航请求。";
        ErrorPagePanel.Visibility = Visibility.Visible;
        e.Handled = true;
    }

    private void Window_Closing(object? sender, CancelEventArgs e) => _host.RejectPendingNavigation();

    private void SetNavigationControlsEnabled(bool isEnabled)
    {
        AddressBar.IsEnabled = isEnabled;
        OpenButton.IsEnabled = isEnabled;
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

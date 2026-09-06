namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Input;
using Aegis.Windows.Broker;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

/// <summary>InPrivate 无痕窗口（P1——对齐 Edge）：独立临时 WebView2 环境（隔离
/// cookie/缓存），多标签；不写历史、不写会话、不落盘任何数据；关闭后清理临时目录。
/// 导航仍全量经 Broker 决策（无桥架构不变）。</summary>
public partial class InPrivateWindow : Window
{
    private readonly BrowserPolicyBroker _broker = new();
    private readonly TabManager _tabs = new();
    private readonly Dictionary<string, TabRuntime> _runtimes = new();
    private string? _activeTabId;
    private bool _suppressSelection;

    private const string HomeUrl = Ntp.NtpAssets.Url;

    public InPrivateWindow()
    {
        InitializeComponent();
        _tabs.TabOpened += CreateRuntime;
        _tabs.TabClosed += OnTabClosed;
        _tabs.TabSwitched += OnTabSwitched;
        TabStrip.ItemsSource = _tabs.Tabs;
        _tabs.NewTab(HomeUrl);
    }

    private async void CreateRuntime(Tab tab)
    {
        var env = await WebView.WebViewEnvironment.InPrivateAsync();
        var runtime = new TabRuntime(_broker, tab, env);
        _runtimes[tab.TabId] = runtime;
        runtime.Control.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
                return;
            var core = runtime.Control.CoreWebView2;
            BindVirtualHosts(core);
            runtime.OnCoreReady(core);
            if (Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
            {
                var target = tab.Url;
                Dispatcher.BeginInvoke(() =>
                {
                    if (_runtimes.ContainsKey(tab.TabId))
                        runtime.Control.Source = new Uri(target);
                });
            }
            else
            {
                runtime.Control.Source = new Uri(tab.Url);
            }
        };
        runtime.NavigationCompleted += (_, _) => Dispatcher.Invoke(() => SyncAddressBar(tab));
        WebViewHost.Children.Add(runtime.Control);
        await runtime.InitAsync();
    }

    private void BindVirtualHosts(CoreWebView2 core)
    {
        var ntp = Ntp.NtpAssets.ResolveContentRoot();
        if (ntp is not null)
            core.SetVirtualHostNameToFolderMapping(
                Ntp.NtpAssets.HostName, ntp,
                CoreWebView2HostResourceAccessKind.Allow);
        var geo = Ntp.NtpAssets.ResolveGeoRoot();
        if (geo is not null)
            core.SetVirtualHostNameToFolderMapping(
                Ntp.NtpAssets.GeoHostName, geo,
                CoreWebView2HostResourceAccessKind.Allow);
    }

    private void OnTabClosed(string tabId)
    {
        if (_runtimes.Remove(tabId, out var runtime))
        {
            WebViewHost.Children.Remove(runtime.Control);
            try { runtime.Dispose(); } catch (Exception) { }
        }
    }

    private void OnTabSwitched(Tab tab)
    {
        _activeTabId = tab.TabId;
        foreach (var pair in _runtimes)
        {
            var on = pair.Key == _activeTabId;
            System.Windows.Controls.Panel.SetZIndex(pair.Value.Control, on ? 5 : 0);
            pair.Value.Control.Visibility = on ? Visibility.Visible : Visibility.Collapsed;
        }
        WebViewHost.UpdateLayout();
        SyncAddressBar(tab);
        _suppressSelection = true;
        TabStrip.SelectedItem = tab;
        _suppressSelection = false;
    }

    private void SyncAddressBar(Tab tab)
    {
        if (!AddressBar.IsKeyboardFocused)
            AddressBar.Text = tab.Url;
    }

    private void NewTab_Click(object sender, RoutedEventArgs e) => _tabs.NewTab(HomeUrl);

    private void TabClose_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.FrameworkElement fe
            && (fe.Tag as string ?? (fe.DataContext as Tab)?.TabId) is { } id)
            _tabs.CloseTab(id);
    }

    private void TabStrip_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressSelection || TabStrip.SelectedItem is not Tab tab)
            return;
        _tabs.SwitchTo(tab.TabId);
    }

    private void NavigateFromAddressBar()
    {
        var target = Chrome.UrlNormalizer.Normalize(AddressBar.Text, Aegis.Windows.Core.Settings.AppSettings.Load(
            Aegis.Windows.Core.Settings.AppSettings.DefaultPath).SearchEngine);
        if (target is null || _activeTabId is null || !_runtimes.TryGetValue(_activeTabId, out var rt))
            return;
        rt.Control.Source = new Uri(target);
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }

    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e) =>
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;

    private void Back_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
            r.Control.GoBack();
    }
    private void Forward_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
            r.Control.GoForward();
    }
    private void Refresh_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r))
            r.Control.Reload();
    }

    private void CloseWindow_Click(object sender, RoutedEventArgs e) => Close();

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
        {
            Close();
            e.Handled = true;
        }
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        foreach (var runtime in _runtimes.Values)
        {
            WebViewHost.Children.Remove(runtime.Control);
            try { runtime.Dispose(); } catch (Exception) { }
        }
        _runtimes.Clear();
        _broker.Dispose();
        WebView.WebViewEnvironment.CleanupInPrivate();
    }
}
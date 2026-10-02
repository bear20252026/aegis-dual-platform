namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using Aegis.Windows.Broker;
using Aegis.Windows.Core;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Security;
using Aegis.Windows.Core.Settings;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

// CS-377（2026-10-02 审计）：MainWindow 上帝文件拆分（1424 行→每文件 ≤500）
// ——本文件为 partial 扩展：纯代码移动，零行为变化（WindowSharedChrome.cs
//  同款先例）。职责：右键菜单与工具栏入口（标签条菜单/收藏☆/二级窗口打开/导航按钮/审批面板）
public partial class MainWindow
{
    private void TabStrip_ContextMenuOpening(object sender, System.Windows.Controls.ContextMenuEventArgs e)
    {
        if (TabItemAt(Mouse.GetPosition(TabStrip)) is not Core.Tabs.Tab tab)
            return;
        TabStrip.ContextMenu ??= new System.Windows.Controls.ContextMenu();
        var menu = TabStrip.ContextMenu;
        menu.Items.Clear();
        // CS-258：绑定快捷键的菜单项补 InputGestureText（未绑定项不虚标）
        var close = new System.Windows.Controls.MenuItem { Header = "关闭标签", InputGestureText = "Ctrl+W" };
        close.Click += (_, _) => _tabs.CloseTab(tab.TabId);
        var closeOthers = new System.Windows.Controls.MenuItem { Header = "关闭其他标签" };
        closeOthers.Click += (_, _) => _tabs.CloseOthers(tab.TabId);
        var closeRight = new System.Windows.Controls.MenuItem { Header = "关闭右侧标签" };
        closeRight.Click += (_, _) => _tabs.CloseRight(tab.TabId);
        var pin = new System.Windows.Controls.MenuItem { Header = tab.IsPinned ? "取消固定标签" : "固定标签" };
        pin.Click += (_, _) => _tabs.SetPinned(tab.TabId, !tab.IsPinned);
        var dup = new System.Windows.Controls.MenuItem { Header = "复制标签" };
        dup.Click += (_, _) => _tabs.Duplicate(tab.TabId);
        var reopen = new System.Windows.Controls.MenuItem
        {
            Header = _tabs.ClosedCount > 0 ? "重新打开已关闭的标签" : "重新打开已关闭的标签（无）",
            IsEnabled = _tabs.ClosedCount > 0,
            // CS-407（2026-10-02 审计）：补 InputGestureText——快捷键 Ctrl+Shift+T
            // 已在 Window_PreviewKeyDown 绑定（CS-258 口径：绑定了快捷键的菜单项
            // 不虚标，未绑定的不冒充——此项属于前者）
            InputGestureText = "Ctrl+Shift+T",
        };
        reopen.Click += (_, _) => ReopenClosedTab();
        menu.Items.Add(close);
        menu.Items.Add(closeOthers);
        menu.Items.Add(closeRight);
        menu.Items.Add(new System.Windows.Controls.Separator());
        menu.Items.Add(pin);
        menu.Items.Add(dup);
        menu.Items.Add(new System.Windows.Controls.Separator());
        menu.Items.Add(reopen);
    }

    private void ReopenClosedTab()
    {
        var s = _tabs.PopClosed();
        if (s is not null)
            _tabs.NewTab(s.Url, s.Title);
    }

    private void TabStrip_PreviewMouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Middle || e.ButtonState != MouseButtonState.Pressed)
            return;
        if (TabItemAt(e.GetPosition(TabStrip)) is Core.Tabs.Tab tab)
        {
            _tabs.CloseTab(tab.TabId);
            e.Handled = true;
        }
    }

    // —— InPrivate ——
    private void InPrivate_Click(object sender, RoutedEventArgs e) => OpenInPrivateNew();

    private void OpenInPrivateNew() => new InPrivateWindow(_settings.SearchEngine).Show();  // CS-224

    /// <summary>M2 收藏☆：toggle 当前页（零页面可控参数——URL/标题服务端取，
    /// 与 Android AegisBridge/Python toggle_bookmark 同安全模型）。</summary>
    private void Star_Click(object sender, RoutedEventArgs e)
    {
        var tab = _tabs.Current;
        if (tab is null || !Uri.TryCreate(tab.Url, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            ShowFeedback("当前页面不支持收藏", isWarning: true);
            return;
        }
        // CS-228：内部虚拟主机页（NTP/画板）排除——地址仅本进程 WebView 可解析，
        // 落书签后任何语境都无法打开
        if (Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
        {
            ShowFeedback("内部页面不支持收藏", isWarning: true);
            return;
        }
        var wasStarred = _bookmarks.Contains(tab.Url);
        // CS-383（2026-10-02 审计）：书签库写入补异常防护（对齐 CS-164
        // BookmarkManagerWindow 守卫）——库锁/磁盘异常此前直接沿 UI 事件炸窗；
        // 失败可见反馈 + SecurityLog 留痕
        bool ok;
        try
        {
            ok = wasStarred
                ? _bookmarks.Remove(tab.Url)
                : _bookmarks.Add(string.IsNullOrWhiteSpace(tab.Title) ? uri.Host : tab.Title, tab.Url);
        }
        catch (Exception ex)
        {
            Core.Security.SecurityLog.Write(
                $"[bookmark] 收藏切换失败（已捕获）: {ex.GetType().Name}: {ex.Message}");
            ShowFeedback($"收藏操作失败：{ex.Message}", isWarning: true);
            return;
        }
        ShowFeedback(ok ? (wasStarred ? "已取消收藏" : "已收藏") : "操作失败", isWarning: !ok);
    }

    private void Settings_Click(object sender, RoutedEventArgs e)
    {
        if (_settingsWindow is null || !_settingsWindow.IsLoaded)
        {
            _settingsWindow = new SettingsWindow(_settings, _broker, this, _settingsService) { Owner = this };
            // 创建即换肤——此前漏调：浅色模式下首次打开设置窗仍深色，直到下次
            // 全局换肤才纠正（对比历史/书签/下载三处创建时都有）
            _settingsWindow.ApplyTheme(_settings.Theme);
        }
        _settingsWindow.Show();
        _settingsWindow.Activate();
    }

    /// <summary>在当前激活标签导航到指定 URL（供书签管理器等调用）。</summary>
    public void OpenInActiveTab(string url)
    {
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var runtime))
            TabRuntime.Navigate(runtime, url);
    }

    private void BookmarkManager_Click(object sender, RoutedEventArgs e)
    {
        if (_bookmarkManagerWindow is null || !_bookmarkManagerWindow.IsLoaded)
        {
            _bookmarkManagerWindow = new BookmarkManagerWindow(_bookmarks, this) { Owner = this };
            _bookmarkManagerWindow.ApplyTheme(_settings.Theme);
        }
        _bookmarkManagerWindow.Show();
        _bookmarkManagerWindow.Activate();
    }

    private void History_Click(object sender, RoutedEventArgs e)
    {
        if (_historyWindow is null || !_historyWindow.IsLoaded)
        {
            _historyWindow = new HistoryWindow(_history) { Owner = this };
            _historyWindow.ApplyTheme(_settings.Theme);
        }
        _historyWindow.Show();
        _historyWindow.Activate();
    }

    /// <summary>M4 下载管理面板（共享数据源——新下载自动进入列表）。</summary>
    private void Downloads_Click(object sender, RoutedEventArgs e)
    {
        if (_downloadsWindow is null || !_downloadsWindow.IsLoaded)
        {
            _downloadsWindow = new DownloadsWindow(_downloads) { Owner = this };
            _downloadsWindow.ApplyTheme(_settings.Theme);
        }
        _downloadsWindow.Show();
        _downloadsWindow.Activate();
    }

    private void Back_Click(object sender, RoutedEventArgs e) => ActiveControl()?.GoBack();
    private void Forward_Click(object sender, RoutedEventArgs e) => ActiveControl()?.GoForward();
    private void Refresh_Click(object sender, RoutedEventArgs e) => ActiveControl()?.Reload();
    private void Stop_Click(object sender, RoutedEventArgs e) => ActiveControl()?.Stop();
    /// <summary>主页（Edge 对齐：回到新标签页，导航仍经 broker 决策）。</summary>
    private void Home_Click(object sender, RoutedEventArgs e)
    {
        if (ActiveRuntime() is { } runtime)
            TabRuntime.Navigate(runtime, HomeUrl);
    }

    /// <summary>个人资料占位：无账号体系，点击聚焦地址栏（对齐 Edge 圆钮位置）。</summary>
    private void Profile_Click(object sender, RoutedEventArgs e)
    {
        AddressBar.Focus();
        AddressBar.SelectAll();
    }

    // ================= 导航确认面板（逻辑在 ApprovalPanelController） =================

    private void ApprovalAllow_Click(object sender, RoutedEventArgs e) => _approval.Allow();

    private void ApprovalDeny_Click(object sender, RoutedEventArgs e) => _approval.Deny();

    private void ShowRejection(string message)
    {
        ErrorPage.Text = message;
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

}

# -*- coding: utf-8 -*-
"""一次性补丁：MainWindow P0+P1 集成（方法块 + 构造接线 + 导航/快捷键/关闭接线）。"""
import pathlib

P = pathlib.Path("windows/src/Aegis.Windows.App/Chrome/MainWindow.xaml.cs")
t = P.read_text(encoding="utf-8")

# 1) 字段声明（插到 _downloads 后）
old_fields = "    private readonly System.Collections.ObjectModel.ObservableCollection<Core.Downloads.DownloadItem> _downloads = new();\n"
new_fields = old_fields + """    private System.Windows.Threading.DispatcherTimer? _sleepTimer;
    private System.Windows.Threading.DispatcherTimer? _suggestTimer;\n"""
assert old_fields in t
t = t.replace(old_fields, new_fields, 1)

# 2) 构造接线（在 InitEngineCombo(); 后）
old_ctor = "        InitEngineCombo();\n    }"
new_ctor = """        InitEngineCombo();
        ZoomStore.Load(_settings.ZoomByHost);
        ZoomStore.Changed += () => Dispatcher.Invoke(() => _settings.ZoomByHost = ZoomStore.Snapshot());
        Core.Privacy.PrivacySettings.ProtectionLevel = _settings.ProtectionLevel;
        Core.Privacy.PrivacySettings.HttpsOnly = _settings.HttpsOnly;
        Core.Privacy.PrivacySettings.SecureDns = _settings.SecureDns;
        RestoreWindowState();
        StartSleepTimer();
        // 建议定时器单例（Tick 由 ResetSuggestTimer 挂/摘）
        _suggestTimer = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromMilliseconds(150) };
        _suggestTimer.Tick += (_, _) => RunSuggestions();
    }

    private void StartSleepTimer()
    {
        _sleepTimer = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(30) };
        _sleepTimer.Tick += (_, _) => SleepCheck();
        _sleepTimer.Start();
    }"""
assert old_ctor in t
t = t.replace(old_ctor, new_ctor, 1)

# 3) InitCompleted 补普通站点导航 else 分支
old_nav = """            if (Chrome.Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
            {
                var targetUrl = tab.Url;
                Dispatcher.BeginInvoke(() =>
                {
                    // 若该标签在延迟导航前已被关闭（销毁），直接跳过设置——否则
                    // 在已释放控件上设 Source 会抛异常，导致「新建标签删不掉」。
                    if (_runtimes.TryGetValue(tab.TabId, out var current) && ReferenceEquals(current, runtime))
                        runtime.Control.Source = new Uri(targetUrl);
                });
            }"""
new_nav = """            if (Chrome.Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
            {
                var targetUrl = tab.Url;
                Dispatcher.BeginInvoke(() =>
                {
                    // 若该标签在延迟导航前已被关闭（销毁），直接跳过设置——否则
                    // 在已释放控件上设 Source 会抛异常，导致「新建标签删不掉」。
                    if (_runtimes.TryGetValue(tab.TabId, out var current) && ReferenceEquals(current, runtime))
                        runtime.Control.Source = new Uri(targetUrl);
                });
            }
            else if (!_restoring)
            {
                // 普通站点：初始化（含虚拟主机映射）就绪后立即导航
                runtime.Control.Source = new Uri(tab.Url);
            }"""
assert old_nav in t
t = t.replace(old_nav, new_nav, 1)

# 4) Window_Closing 保存窗口状态 + 落盘缩放
old_close = """    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        SaveSession();
        foreach (var runtime in _runtimes.Values)
            runtime.Host.RejectPendingNavigation();
    }"""
new_close = """    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        SaveSession();
        SaveWindowState();
        _settings.ZoomByHost = ZoomStore.Snapshot();
        _settings.Save(AppSettings.DefaultPath);
        foreach (var runtime in _runtimes.Values)
            runtime.Host.RejectPendingNavigation();
    }"""
assert old_close in t
t = t.replace(old_close, new_close, 1)

# 5) 快捷键：Ctrl+F 查找 / Ctrl+0 重置缩放 / Ctrl+=/- 缩放（追加到既有 Ctrl 分支后）
old_keys = """                case Key.U:
                    OpenSourceViewer();
                    e.Handled = true;
                    return;
            }
        }"""
new_keys = """                case Key.U:
                    OpenSourceViewer();
                    e.Handled = true;
                    return;
                case Key.F:
                    OpenFind();
                    e.Handled = true;
                    return;
                case Key.D0:
                case Key.NumPad0:
                    ActiveRuntime()?.ResetZoom();
                    e.Handled = true;
                    return;
                case Key.OemPlus:
                case Key.Add:
                    ZoomActive(0.1);
                    e.Handled = true;
                    return;
                case Key.OemMinus:
                case Key.Subtract:
                    ZoomActive(-0.1);
                    e.Handled = true;
                    return;
            }
        }"""
assert old_keys in t
t = t.replace(old_keys, new_keys, 1)

# 6) 追加方法块：睡眠/右键菜单/中键/查找/补全/InPrivate/窗口状态
methods = '''

    private TabRuntime? ActiveRuntime() =>
        _activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r) ? r : null;

    private void ZoomActive(double delta)
    {
        var rt = ActiveRuntime();
        if (rt?.Control.CoreWebView2 is null)
            return;
        var host = Uri.TryCreate(rt.Control.CoreWebView2.Source, UriKind.Absolute, out var u)
            ? u.Host : null;
        var z = Math.Clamp(rt.Control.ZoomFactor + delta, 0.25, 3.0);
        rt.Control.ZoomFactor = z;
        if (host is not null)
            Core.Tabs.ZoomStore.Set(host, z);
    }

    private void SleepCheck()
    {
        var minutes = _settings.SleepMinutes;
        if (minutes <= 0 || _activeTabId is null)
            return;
        var now = DateTime.Now;
        foreach (var tab in _tabs.Tabs.ToList())
        {
            if (tab.IsPinned || tab.IsSleeping || tab.TabId == _activeTabId)
                continue;
            if ((now - tab.LastActivated).TotalMinutes >= minutes
                && _runtimes.TryGetValue(tab.TabId, out var runtime))
            {
                WebViewHost.Children.Remove(runtime.Control);
                try { runtime.Dispose(); } catch (Exception) { }
                _runtimes.Remove(tab.TabId);
                tab.IsSleeping = true;
            }
        }
    }

    private void WakeTab(Tab tab)
    {
        if (_runtimes.ContainsKey(tab.TabId))
            return;
        tab.IsSleeping = false;
        CreateRuntime(tab, tab.Url);
    }

    private static Core.Tabs.Tab? TabItemAt(System.Windows.Point p)
    {
        var element = TabStrip.InputHitTest(p) as DependencyObject;
        while (element is not null && element is not System.Windows.Controls.ListBoxItem)
            element = System.Windows.Media.VisualTreeHelper.GetParent(element);
        return (element as System.Windows.Controls.ListBoxItem)?.DataContext as Core.Tabs.Tab;
    }

    private void TabStrip_ContextMenuOpening(object sender, ContextMenuEventArgs e)
    {
        if (TabItemAt(Mouse.GetPosition(TabStrip)) is not Core.Tabs.Tab tab)
            return;
        TabStrip.ContextMenu ??= new System.Windows.Controls.ContextMenu();
        var menu = TabStrip.ContextMenu;
        menu.Items.Clear();
        var close = new System.Windows.Controls.MenuItem { Header = "关闭标签" };
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
        if (e.ChangedButton != MouseButtonState.Middle || e.ButtonState != MouseButtonState.Pressed)
            return;
        if (TabItemAt(e.GetPosition(TabStrip)) is Core.Tabs.Tab tab)
        {
            _tabs.CloseTab(tab.TabId);
            e.Handled = true;
        }
    }

    // —— 页内查找 ——
    private void OpenFind()
    {
        FindBar.Visibility = Visibility.Visible;
        FindBox.Focus();
        FindBox.SelectAll();
    }
    private void CloseFind()
    {
        FindBar.Visibility = Visibility.Collapsed;
        FindCount.Text = string.Empty;
        if (ActiveRuntime()?.Control.CoreWebView2 is { } cw)
            _ = cw.ExecuteScriptAsync("window.find('', false, false, false);");
    }
    private async void Find_Executed(object sender, RoutedEventArgs e)
    {
        var query = FindBox.Text;
        if (string.IsNullOrWhiteSpace(query) || ActiveRuntime()?.Control.CoreWebView2 is not { } cw)
            return;
        var backwards = (e.OriginalSource as System.Windows.Controls.Button)?.Tag as string == "b";
        try
        {
            var count = await CountMatches(cw, query);
            await cw.ExecuteScriptAsync(BuildFindJs(query, backwards));
            FindCount.Text = count > 0 ? $"{count} 处" : "无结果";
        }
        catch (Exception) { }
    }
    private static async Task<int> CountMatches(CoreWebView2 cw, string query)
    {
        var q = System.Text.Json.JsonSerializer.Serialize(query);
        var js = "new Promise(r=>{try{var m=(document.body&&document.body.innerText)||'';" +
                 "var n=0,i=0,Q=" + q + ";while((i=m.indexOf(Q,i))!==-1){n++;i+=Q.length;}r(n);}catch(e){r(0);}});";
        var res = await cw.ExecuteScriptAsync(js);
        return int.TryParse(res, out var n) ? n : 0;
    }
    private static string BuildFindJs(string query, bool backwards) =>
        "window.find(" + System.Text.Json.JsonSerializer.Serialize(query) +
        ", false, " + (backwards ? "true" : "false") + ", true);";

    // —— 地址栏自动补全 ——
    private void RunSuggestions()
    {
        _suggestTimer?.Stop();
        var query = AddressBar.Text.Trim();
        if (string.IsNullOrEmpty(query))
        {
            SuggestionPopup.IsOpen = false;
            return;
        }
        var rows = BuildSuggestions(query);
        SuggestionList.ItemsSource = rows;
        SuggestionPopup.IsOpen = rows.Count > 0;
    }
    private List<SuggestionRow> BuildSuggestions(string query)
    {
        var q = query.ToLowerInvariant();
        var rows = new List<SuggestionRow>();
        foreach (var b in _bookmarks.All())
            if (b.Title.ToLowerInvariant().Contains(q) || b.Url.ToLowerInvariant().Contains(q))
                rows.Add(new SuggestionRow(b.Url, string.IsNullOrWhiteSpace(b.Title) ? b.Url : b.Title, "书签"));
        foreach (var h in _history.Search(q, null, 60))
        {
            if (h.Url.ToLowerInvariant().Contains(q)
                && !rows.Any(r => string.Equals(r.Url, h.Url, StringComparison.Ordinal)))
            {
                rows.Add(new SuggestionRow(h.Url, string.IsNullOrWhiteSpace(h.Title) ? h.Url : h.Title, "历史"));
                if (rows.Count >= 8) break;
            }
        }
        return rows.Take(8).ToList();
    }
    public sealed record SuggestionRow(string Url, string Title, string Kind);

    private void SuggestPick(SuggestionRow row)
    {
        SuggestionPopup.IsOpen = false;
        AddressBar.Text = row.Url;
        AddressBar.CaretIndex = row.Url.Length;
        NavigateFromAddressBar();
    }
    private void SuggestionList_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && SuggestionList.SelectedItem is SuggestionRow sel)
        {
            SuggestPick(sel);
            e.Handled = true;
        }
        else if (e.Key == Key.Escape)
        {
            SuggestionPopup.IsOpen = false;
            e.Handled = true;
        }
    }

    // —— InPrivate ——
    private void OpenInPrivateNew() => new InPrivateWindow().Show();

    // —— 窗口状态记忆 ——
    private void SaveWindowState()
    {
        _settings.WindowMaximized = WindowState == WindowState.Maximized;
        if (WindowState == WindowState.Normal)
        {
            _settings.WindowLeft = Left;
            _settings.WindowTop = Top;
            _settings.WindowWidth = Width;
            _settings.WindowHeight = Height;
        }
    }
    private void RestoreWindowState()
    {
        var sw = SystemParameters.VirtualScreenWidth;
        var sh = SystemParameters.VirtualScreenHeight;
        Width = _settings.WindowWidth > 400 ? _settings.WindowWidth : 1200;
        Height = _settings.WindowHeight > 300 ? _settings.WindowHeight : 800;
        if (!double.IsNaN(_settings.WindowLeft) && !double.IsNaN(_settings.WindowTop)
            && _settings.WindowLeft < sw && _settings.WindowTop < sh)
        {
            Left = _settings.WindowLeft;
            Top = _settings.WindowTop;
        }
        if (_settings.WindowMaximized)
            WindowState = WindowState.Maximized;
    }
'''
# 方法块插到"会话持久化"区之前
anchor = "    // ================= 会话持久化 ================="
assert anchor in t
t = t.replace(anchor, methods + "\n" + anchor, 1)

# 8) 地址栏键盘：建议弹出时 上下选择/回车跳转/Esc 收起；否则回车导航
old_key = """    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }"""
new_key = """    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (SuggestionPopup.IsOpen && SuggestionList.Items.Count > 0)
        {
            if (e.Key == Key.Down)
            {
                SuggestionList.SelectedIndex = (SuggestionList.SelectedIndex + 1) % SuggestionList.Items.Count;
                e.Handled = true; return;
            }
            if (e.Key == Key.Up)
            {
                SuggestionList.SelectedIndex = (SuggestionList.SelectedIndex - 1 + SuggestionList.Items.Count) % SuggestionList.Items.Count;
                e.Handled = true; return;
            }
            if (e.Key == Key.Enter && SuggestionList.SelectedItem is SuggestionRow sel)
            {
                SuggestPick(sel);
                e.Handled = true; return;
            }
            if (e.Key == Key.Escape)
            {
                SuggestionPopup.IsOpen = false;
                e.Handled = true; return;
            }
        }
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }"""
assert old_key in t, "AddressBar_KeyDown not found"
t = t.replace(old_key, new_key, 1)

# 9) 替换既有地址栏 TextChanged：触发补全建议
old_abt = """    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e) =>
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;"""
new_abt = """    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        _suggestTimer?.Stop();
        _suggestTimer?.Start();
    }"""
assert old_abt in t, "AddressBar_TextChanged not found"
t = t.replace(old_abt, new_abt, 1)

P.write_text(t, encoding="utf-8", newline="")
print("MainWindow patched OK")

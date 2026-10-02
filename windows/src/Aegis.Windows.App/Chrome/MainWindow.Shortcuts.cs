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
//  同款先例）。职责：快捷键与地址栏（Window_PreviewKeyDown 全量路由/查找条/建议弹层/地址栏导航）
public partial class MainWindow
{
    // —— 页内查找（逻辑在 FindBarController——上帝对象拆分第一批） ——
    private void FindBox_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(FindBox.Text))
            _ = _find.SearchAsync(FindBox.Text, backwards: false);
    }

    private async void Find_Executed(object sender, RoutedEventArgs e)
    {
        var backwards = (e.OriginalSource as System.Windows.Controls.Button)?.Tag as string == "b";
        await _find.SearchAsync(FindBox.Text, backwards);
    }

    private void CloseFind_Click(object sender, RoutedEventArgs e) => _find.Close();

    // —— 地址栏自动补全（逻辑在 SuggestionController） ——
    private void SuggestionList_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && _suggest.Selected() is { } sel)
        {
            _suggest.Pick(sel);
            e.Handled = true;
        }
        else if (e.Key == Key.Escape)
        {
            _suggest.Close();
            e.Handled = true;
        }
    }

    /// <summary>鼠标点击建议项即导航（此前仅键盘可达——鼠标点击只关弹层）。</summary>
    private void SuggestionList_PreviewMouseLeftButtonUp(object sender, MouseButtonEventArgs e)
    {
        if (_suggest.Selected() is { } sel)
        {
            _suggest.Pick(sel);
            e.Handled = true;
        }
    }


    // ================= 地址栏与导航 =================

    private void AddressBar_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        AddressHint.Visibility = AddressBar.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        _suggest.OnTextChanged();
    }

    /// <summary>M1：地址栏获得焦点即全选（Ctrl+L 与鼠标点击同语义——
    /// 对齐 Python shell_toolbar 聚焦选中契约）。</summary>
    private void AddressBar_GotKeyboardFocus(object sender, KeyboardFocusChangedEventArgs e) =>
        AddressBar.SelectAll();

    private void SyncAddressBar(string url)
    {
        if (!AddressBar.IsKeyboardFocused)
            AddressBar.Text = url;
    }

    private void NavigateFromAddressBar()
    {
        // 输入归一单源（UrlNormalizer——与 Android SearchEngines.kt 跨端契约对齐）；
        // 最终仍经该标签 HostWebView 的 NavigationStarting → Broker 决策。
        var target = UrlNormalizer.Normalize(AddressBar.Text, _settings.SearchEngine);
        if (target is null)
        {
            // CS-288：fail-closed 拒绝留审计——非导航协议尝试是安全相关事件
            Core.Security.SecurityLog.Write("[nav] 地址栏归一拒绝（空输入或非导航协议）");
            ErrorPage.Text = "无法导航：输入为空，或属于非导航协议（file:/javascript:/data: 等已被拒绝）。";
            ErrorPagePanel.Visibility = Visibility.Visible;
            return;
        }
        // 归一器已保证产物可被 Uri 解析；此处兜底捕获非法输入（此前直接
        // new Uri(target)，"http://" 类输入抛 UriFormatException）
        if (_activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var runtime))
        {
            if (!TabRuntime.Navigate(runtime, target))
            {
                ErrorPage.Text = "无法导航：地址无效。";
                ErrorPagePanel.Visibility = Visibility.Visible;
            }
        }
    }

    private void AddressBar_KeyDown(object sender, KeyEventArgs e)
    {
        if (_suggest.IsOpenWithItems)
        {
            if (e.Key == Key.Down)
            {
                _suggest.MoveSelection(1);
                e.Handled = true; return;
            }
            if (e.Key == Key.Up)
            {
                _suggest.MoveSelection(-1);
                e.Handled = true; return;
            }
            if (e.Key == Key.Enter && _suggest.Selected() is { } sel)
            {
                _suggest.Pick(sel);
                e.Handled = true; return;
            }
            if (e.Key == Key.Escape)
            {
                _suggest.Close();
                e.Handled = true; return;
            }
        }
        if (e.Key == Key.Enter)
            NavigateFromAddressBar();
    }

    private void Open_Click(object sender, RoutedEventArgs e) => NavigateFromAddressBar();

    private Microsoft.Web.WebView2.Wpf.WebView2? ActiveControl() =>
        _activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r) ? r.Control : null;


    // ================= 快捷键与关闭 =================

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // Ctrl+L 聚焦地址栏 / Ctrl+T 新建 / Ctrl+W 关闭当前（标签条 tooltip 契约）
        if (Keyboard.Modifiers == (ModifierKeys.Control | ModifierKeys.Shift))
        {
            if (e.Key == Key.Tab)
            {
                CycleTab(-1);
                e.Handled = true;
                return;
            }
            if (e.Key == Key.T)
            {
                ReopenClosedTab();
                e.Handled = true;
                return;
            }
        }
        else if (Keyboard.Modifiers == ModifierKeys.Control)
        {
            switch (e.Key)
            {
                case Key.L:
                    AddressBar.Focus();
                    AddressBar.SelectAll();
                    e.Handled = true;
                    return;
                case Key.T:
                    _tabs.NewTab(HomeUrl);
                    e.Handled = true;
                    return;
                case Key.W when _tabs.CurrentTabId is not null:
                    _tabs.CloseTab(_tabs.CurrentTabId);
                    e.Handled = true;
                    return;
                case Key.U:
                    OpenSourceViewer();
                    e.Handled = true;
                    return;
                case Key.F:
                    _find.Open();
                    e.Handled = true;
                    return;
                case Key.H:
                    History_Click(this, e);
                    e.Handled = true;
                    return;
                case Key.J:
                    Downloads_Click(this, e);
                    e.Handled = true;
                    return;
                case Key.D:
                    Star_Click(this, e);
                    e.Handled = true;
                    return;
                case Key.R:
                    ActiveControl()?.Reload();
                    e.Handled = true;
                    return;
                case Key.Tab:
                    CycleTab(1);
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
                // Ctrl+1..8 直达标签 / Ctrl+9 末位标签（Edge 契约）
                case Key.D1 or Key.D2 or Key.D3 or Key.D4 or Key.D5
                     or Key.D6 or Key.D7 or Key.D8 or Key.D9
                     or Key.NumPad1 or Key.NumPad2 or Key.NumPad3 or Key.NumPad4 or Key.NumPad5
                     or Key.NumPad6 or Key.NumPad7 or Key.NumPad8 or Key.NumPad9:
                    JumpToTabByKey(e.Key);
                    e.Handled = true;
                    return;
            }
        }
        else if (Keyboard.Modifiers == ModifierKeys.Alt)
        {
            // Alt+←/→ 历史
            if (e.Key == Key.Left)
            {
                ActiveControl()?.GoBack();
                e.Handled = true;
                return;
            }
            if (e.Key == Key.Right)
            {
                ActiveControl()?.GoForward();
                e.Handled = true;
                return;
            }
        }
        else if (Keyboard.Modifiers == ModifierKeys.None)
        {
            switch (e.Key)
            {
                case Key.F5:
                    ActiveControl()?.Reload();
                    e.Handled = true;
                    return;
                case Key.F6:
                    AddressBar.Focus();
                    AddressBar.SelectAll();
                    e.Handled = true;
                    return;
                case Key.Tab:
                    // 无修饰 Tab 由 WPF 焦点遍历处理（地址栏/查找框间移动）
                    break;
            }
        }
        // CS-390（2026-10-02 审计）：查找条可见时 Esc 先关查找条——关闭钮
        // ToolTip 承诺「关闭（Esc）」，此前 Esc 只路由审批面板（承诺不可达）
        if (e.Key == Key.Escape && FindBar.Visibility == Visibility.Visible)
        {
            _find.Close();
            e.Handled = true;
            return;
        }
        if (!_approval.IsVisible || e.Key != Key.Escape)
            return;
        _approval.Deny();
        e.Handled = true;
    }

    /// <summary>Ctrl+Tab / Ctrl+Shift+Tab 循环切换标签。</summary>
    private void CycleTab(int direction)
    {
        var count = _tabs.Tabs.Count;
        if (count == 0)
            return;
        // CS-151：就地循环定位——此前 ToList() 全表复制只为找当前索引
        var current = -1;
        if (_tabs.CurrentTabId is { } id)
        {
            for (var i = 0; i < count; i++)
            {
                if (_tabs.Tabs[i].TabId == id)
                {
                    current = i;
                    break;
                }
            }
        }
        _tabs.SwitchTo(_tabs.Tabs[NextIndex(current, direction, count)].TabId);
    }

    /// <summary>CS-158：循环切换的目标索引提纯直测（未找到/负索引钳 0 起算）。</summary>
    internal static int NextIndex(int currentIndex, int direction, int count)
    {
        var current = currentIndex < 0 ? 0 : currentIndex;
        return ((current + direction) % count + count) % count;
    }

    /// <summary>Ctrl+1..8 直达对应标签，Ctrl+9 末位标签。</summary>
    private void JumpToTabByKey(Key key)
    {
        var digit = ToDigit(key);
        if (digit == 0)
            return;
        var index = digit == 9 ? _tabs.Tabs.Count - 1 : digit - 1;
        if (index >= 0 && index < _tabs.Tabs.Count)
            _tabs.SwitchTo(_tabs.Tabs[index].TabId);
    }

    /// <summary>CS-157：数字键 → 序号（1..9，非数字键 0）提纯直测。</summary>
    internal static int ToDigit(Key key) => key switch
    {
        Key.D1 => 1, Key.D2 => 2, Key.D3 => 3, Key.D4 => 4, Key.D5 => 5,
        Key.D6 => 6, Key.D7 => 7, Key.D8 => 8, Key.D9 => 9,
        Key.NumPad1 => 1, Key.NumPad2 => 2, Key.NumPad3 => 3, Key.NumPad4 => 4,
        Key.NumPad5 => 5, Key.NumPad6 => 6, Key.NumPad7 => 7, Key.NumPad8 => 8,
        Key.NumPad9 => 9,
        _ => 0,
    };

}

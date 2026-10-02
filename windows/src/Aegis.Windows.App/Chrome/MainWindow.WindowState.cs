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
//  同款先例）。职责：窗口状态记忆与关闭链（Save/RestoreWindowState/Window_Closing/OnClosed）
public partial class MainWindow
{
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
        var vsl = SystemParameters.VirtualScreenLeft;
        var vst = SystemParameters.VirtualScreenTop;
        // CS-067：下界防残窗，上界钳到虚拟屏幕——持久化值被外部
        // 篡改成超大数（如 int.MaxValue）时不再撑出不可操作的巨型窗口
        // CS-150：回退宽高引用快照级单源常量（CS-123），下界为窗口级命名常量
        Width = _settings.WindowWidth > MinRestoredWidth
            ? Math.Min(_settings.WindowWidth, sw)
            : Core.Settings.BrowserSettingsSnapshot.DefaultWindowWidth;
        Height = _settings.WindowHeight > MinRestoredHeight
            ? Math.Min(_settings.WindowHeight, sh)
            : Core.Settings.BrowserSettingsSnapshot.DefaultWindowHeight;
        // CS-298（2026-09-26 审计）：Left/Top 此前只校验上界（<sw/<sh，且比
        // 的是尺寸而非坐标原点）——负值（NormalizeWindow 允许持久化到
        // -100000）可把窗口恢复到虚拟屏幕外不可见。改为完整区间校验
        // [VirtualScreenLeft, VirtualScreenLeft+ScreenWidth-Width]（Top 同理），
        // 越界回退虚拟屏幕居中
        var maxLeft = vsl + sw - Width;
        var maxTop = vst + sh - Height;
        if (!double.IsNaN(_settings.WindowLeft) && !double.IsNaN(_settings.WindowTop)
            && _settings.WindowLeft >= vsl && _settings.WindowLeft <= maxLeft
            && _settings.WindowTop >= vst && _settings.WindowTop <= maxTop)
        {
            Left = _settings.WindowLeft;
            Top = _settings.WindowTop;
        }
        else
        {
            Left = vsl + (sw - Width) / 2;
            Top = vst + (sh - Height) / 2;
        }
        if (_settings.WindowMaximized)
            WindowState = WindowState.Maximized;
    }

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        // CS-156：FlushSession 保留 OnClosed 单点——Closing 在未取消时必达
        // Closed，此前两处各落盘一次（每次关闭双份 SQLite 写）
        SaveWindowState();
        _settings.ZoomByHost = ZoomStore.Snapshot();
        _settingsService.Apply(_settings);
        foreach (var runtime in _runtimes.Values)
            runtime.Host.RejectPendingNavigation();
    }

    private void SetNavigationControlsEnabled(bool isEnabled)
    {
        AddressBar.IsEnabled = isEnabled;
        OpenButton.IsEnabled = isEnabled;
        BackButton.IsEnabled = isEnabled;
        ForwardButton.IsEnabled = isEnabled;
        RefreshButton.IsEnabled = isEnabled;
        StopButton.IsEnabled = isEnabled;
        HomeButton.IsEnabled = isEnabled;
    }

    protected override void OnClosed(EventArgs e)
    {
        FlushSession();
        // CS-387（2026-10-02 审计）：关窗前同步等待后台历史写入链尾（带 2s 超时
        // 兜底——卡死也不永久挂起关窗；写链内部已吞异常，超时丢弃的写入由
        // 下次导航的追加语义自然补齐）——此前进程随窗口退出时未落盘的历史
        // 写入被静默丢弃
        _ = _historyWriteTail.Wait(TimeSpan.FromSeconds(2));
        // 审计修复：停全部定时器 + 解绑事件——主窗口关闭但 InPrivate 存活时，
        // 此前 30s 睡眠巡检/建议定时器继续空转、ZoomStore.Changed 永久持有
        // 对已关窗口的引用（内存泄漏）
        _sleepTimer?.Stop();
        _suggest.StopDebounce();
        _feedbackTimer?.Stop();
        if (_zoomChangedHandler is not null)
            ZoomStore.Changed -= _zoomChangedHandler;
        // CS-367：解绑 KillSwitch 横幅订阅（横幅句柄不再持有已关窗口）
        _broker.KillSwitch.Engaged -= _killSwitchEngagedHandler;
        _tabs.TabOpened -= OnTabOpened;
        _tabs.TabClosed -= OnTabClosed;
        _tabs.TabSwitched -= OnTabSwitched;
        _runtimeCoordinator.NtpNavigationFailed -= OnNtpNavigationFailed;
        _sourceViewerWindows.Clear();  // CS-233：源码查看窗引用驻留清理（Owner=本窗）
        // 全部 runtime 经协调器统一销毁（先摘视觉树再释放，令牌一并取消）
        // CS-366（2026-10-01 审计）：_runtimes 清空收敛到协调器 Dispose 单点
        //（此前两调用方各自 Clear——约定分散）
        _runtimeCoordinator.Dispose();
        _broker.Dispose();
        base.OnClosed(e);
    }
}

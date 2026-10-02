namespace Aegis.Windows.Chrome;

using System;
using System.Windows;
using System.Windows.Controls;
/// <summary>CS-370/371（2026-10-01 审计）：主窗与无痕窗两份同形实现单源化
///——此前危险下载确认 MessageBox 与标签切换四属性翻转在两窗各持一份
///逐字相同副本（改口径必漏一处）。</summary>
internal static class WindowSharedChrome
{
    /// <summary>CS-370：危险扩展下载确认对话框（M3——fail-closed：窗口已
    /// 关闭或用户未确认一律拒绝）。downloadUrl/fileName 仅入受信对话框，
    /// 不经任何页面可触达通道。</summary>
    internal static bool ConfirmDangerousDownload(Window owner, string downloadUrl, string fileName)
    {
        if (!owner.IsLoaded)
            return false;
        return MessageBox.Show(
            owner,
            $"此文件的类型可能存在风险，是否允许下载？\n\n文件：{fileName}\n来源：{downloadUrl}",
            "下载确认",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning) == MessageBoxResult.Yes;
    }

    /// <summary>CS-371：标签切换四属性翻转（Z 序/可见性/命中测试/使能）——
    /// WebView2 是 HWND 承载控件：仅切 Visibility 在部分 WPF 版本不足以刷新
    /// 层级，须显式控制 Z 序、命中测试与使能。（WebView2 派生自
    /// FrameworkElement 而非 Control——参数按基类收宽。）</summary>
    internal static void ApplyTabVisibility(FrameworkElement control, bool isActive)
    {
        Panel.SetZIndex(control, isActive ? 5 : 0);
        control.Visibility = isActive ? Visibility.Visible : Visibility.Collapsed;
        control.IsHitTestVisible = isActive;
        control.IsEnabled = isActive;
    }

    /// <summary>CS-411（2026-10-02 审计）：标签关闭单源守卫（主窗与无痕窗共用）
    /// ——主窗有 SecurityLog 留痕 + try/catch 不阻断，无痕窗此前裸调
    /// CloseTab（集合/库异常直接炸窗）。返回是否实际发起了关闭。</summary>
    internal static bool CloseTabSafely(Core.Tabs.TabManager tabs, string? tabId)
    {
        if (string.IsNullOrEmpty(tabId))
            return false;
        Core.Security.SecurityLog.Write($"[tab] 请求关闭标签 {tabId}");
        try
        {
            tabs.CloseTab(tabId);
            return true;
        }
        catch (Exception ex)
        {
            Core.Security.SecurityLog.Write(
                $"[tab] 关闭标签异常（已捕获，不阻断）: {ex.GetType().Name}: {ex.Message}");
            return false;
        }
    }
}

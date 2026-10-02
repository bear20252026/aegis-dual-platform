namespace Aegis.Windows.Chrome;

using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

/// <summary>独立窗口（设置/历史/下载/书签管理）的统一深浅主题应用器。
/// 审计修复：此前每窗口一套 ApplyTheme（或完全没有）——浅色模式下只有主窗口
/// 换肤、其余窗口永远深色；HistoryWindow/SettingsWindow 又各自拼色值（#F5F5F7
/// vs #F2F2F7 不一致）。色板单源在此维护，各窗口一行调用。</summary>
public static class WindowTheme
{
    /// <summary>DWMWA_USE_IMMERSIVE_DARK_MODE（Win10 20H1+/Win11——深色标题栏）。
    /// 修复：独立窗口此前系统白标题栏与深色内容割裂（UI 现代化批）。</summary>
    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    /// <summary>窗口 → 最新标题栏深色态 + SourceInitialized 挂接标记。
    /// ApplyTheme 在 Show 之前调用（句柄未建）——DWM 调用必须推迟到句柄就绪。</summary>
    private static readonly ConditionalWeakTable<Window, CaptionStateBox> CaptionStates = new();

    private sealed class CaptionStateBox
    {
        public bool Dark;
        public bool Hooked;
    }

    /// <summary>把标准画刷键写入窗口资源（iOS 深浅色板，DynamicResource 即时生效），
    /// 并同步深/浅色原生标题栏（DWM 失败静默——旧系统保持默认标题栏）。</summary>
    public static void Apply(Window window, string? theme)
    {
        var light = string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        Set(window, "ChromeBackgroundBrush", light ? "#FFF2F2F7" : "#FF1C1C1E");
        Set(window, "CardBrush", light ? "#FFFFFFFF" : "#FF2C2C2E");
        Set(window, "SeparatorBrush", light ? "#FFE5E5EA" : "#FF38383A");
        Set(window, "SegmentedBrush", light ? "#FFE9E9EB" : "#FF2C2C2E");
        Set(window, "SegmentedSelectedBrush", light ? "#FFFFFFFF" : "#FF5A5A5E");
        Set(window, "FieldBackgroundBrush", light ? "#FFE9E9EB" : "#FF2C2C2E");
        Set(window, "TextPrimaryBrush", light ? "#FF1A1A1A" : "#FFFFFFFF");
        Set(window, "TextSecondaryBrush", light ? "#FF8A8A8E" : "#FF98989F");
        Set(window, "TextMutedBrush", light ? "#FFAEAEB2" : "#FF6C6C70");
        Set(window, "AccentBrush", light ? "#FF007AFF" : "#FF0A84FF");
        Set(window, "AccentSoftBrush", light ? "#1A007AFF" : "#220A84FF");
        Set(window, "DangerBrush", light ? "#FFFF3B30" : "#FFFF453A");
        ApplyCaptionTheme(window, dark: !light);
    }

    /// <summary>深/浅色标题栏。句柄未建（Show 前）时记录状态并挂接
    /// SourceInitialized——句柄就绪后以最新状态补应用；句柄已建（运行时切主题）立即生效。</summary>
    public static void ApplyCaptionTheme(Window window, bool dark)
    {
        var state = CaptionStates.GetOrCreateValue(window);
        state.Dark = dark;
        if (!state.Hooked)
        {
            state.Hooked = true;
            window.SourceInitialized += (_, _) =>
                ApplyCaptionDark(window, CaptionStates.GetOrCreateValue(window).Dark);
        }
        ApplyCaptionDark(window, dark);
    }

    private static void ApplyCaptionDark(Window window, bool dark)
    {
        try
        {
            var hwnd = new WindowInteropHelper(window).Handle;
            if (hwnd == IntPtr.Zero) return;
            var on = dark ? 1 : 0;
            _ = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ref on, sizeof(int));
        }
        catch (Exception)
        {
            // CS-374（2026-10-01 审计）：`catch (Exception _)` 触发 CS0168——
            // 弃元须裸 catch(Exception) 才不占变量名（0 警告基线回归）
            // 旧 Windows / 句柄未建——标题栏保持系统默认，不影响功能
        }
    }

    private static void Set(Window window, string key, string hex) =>
        window.Resources[key] = Core.ThemeColor.ParseBrush(hex);
}

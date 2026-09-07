namespace Aegis.Windows.Chrome;

using System.Windows;

/// <summary>独立窗口（设置/历史/下载/书签管理）的统一深浅主题应用器。
/// 审计修复：此前每窗口一套 ApplyTheme（或完全没有）——浅色模式下只有主窗口
/// 换肤、其余窗口永远深色；HistoryWindow/SettingsWindow 又各自拼色值（#F5F5F7
/// vs #F2F2F7 不一致）。色板单源在此维护，各窗口一行调用。</summary>
public static class WindowTheme
{
    /// <summary>把标准画刷键写入窗口资源（iOS 深浅色板，DynamicResource 即时生效）。</summary>
    public static void Apply(Window window, string? theme)
    {
        var light = string.Equals(theme, "light", System.StringComparison.OrdinalIgnoreCase);
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
    }

    private static void Set(Window window, string key, string hex) =>
        window.Resources[key] = Core.ThemeColor.ParseBrush(hex);
}

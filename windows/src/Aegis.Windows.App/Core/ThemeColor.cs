namespace Aegis.Windows.Core;

using System;
using System.Windows.Media;

/// <summary>共享 ARGB 十六进制色值解析（替代 ColorConverter.ConvertFromString——
/// 该方法在部分环境下对合法色值抛 FormatException「Invalid token」）。
/// MainWindow、HistoryWindow、DateField 统一使用，消除重复实现。</summary>
public static class ThemeColor
{
    /// <summary>解析 #AARRGGBB / #RRGGBB 为 SolidColorBrush（已 Freeze）。
    /// 非法输入回退白色——绝不抛异常。</summary>
    public static SolidColorBrush ParseBrush(string hex)
    {
        var h = hex.TrimStart('#');
        byte a = 0xFF, r = 0xFF, g = 0xFF, b = 0xFF;
        if (h.Length == 8)
        {
            a = ParseHex(h, 0); r = ParseHex(h, 2); g = ParseHex(h, 4); b = ParseHex(h, 6);
        }
        else if (h.Length == 6)
        {
            r = ParseHex(h, 0); g = ParseHex(h, 2); b = ParseHex(h, 4);
        }
        var brush = new SolidColorBrush(Color.FromArgb(a, r, g, b));
        brush.Freeze();
        return brush;
    }

    private static byte ParseHex(string h, int offset) =>
        Convert.ToByte(h.Substring(offset, 2), 16);
}
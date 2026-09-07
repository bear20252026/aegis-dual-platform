namespace Aegis.Windows.Core;

using System;
using System.Globalization;
using System.Windows.Media;

/// <summary>共享 ARGB 十六进制色值解析（替代 ColorConverter.ConvertFromString——
/// 该方法在部分环境下对合法色值抛 FormatException「Invalid token」）。
/// MainWindow/各独立窗口（WindowTheme）统一使用，消除重复实现。</summary>
public static class ThemeColor
{
    /// <summary>解析 #AARRGGBB / #RRGGBB / #RGB / #ARGB（3/4 位短格式按
    /// CSS 语义展开）为 SolidColorBrush（已 Freeze）。
    /// null/空/非法输入回退白色——兑现注释「绝不抛异常」的契约（此前
    /// null 抛 NRE、非十六进制抛 FormatException）。</summary>
    public static SolidColorBrush ParseBrush(string? hex)
    {
        try
        {
            var h = (hex ?? string.Empty).Trim().TrimStart('#');
            byte a = 0xFF, r = 0xFF, g = 0xFF, b = 0xFF;
            switch (h.Length)
            {
                case 8:
                    a = ParseHex(h, 0); r = ParseHex(h, 2); g = ParseHex(h, 4); b = ParseHex(h, 6);
                    break;
                case 6:
                    r = ParseHex(h, 0); g = ParseHex(h, 2); b = ParseHex(h, 4);
                    break;
                case 4:
                    a = Expand(h, 0); r = Expand(h, 1); g = Expand(h, 2); b = Expand(h, 3);
                    break;
                case 3:
                    r = Expand(h, 0); g = Expand(h, 1); b = Expand(h, 2);
                    break;
                // 其它长度（含 10 位 #FFB3FFFFFF 类历史事故形态）——回退白色
            }
            var brush = new SolidColorBrush(Color.FromArgb(a, r, g, b));
            brush.Freeze();
            return brush;
        }
        catch (Exception)
        {
            var fallback = new SolidColorBrush(Colors.White);
            fallback.Freeze();
            return fallback;
        }
    }

    private static byte Expand(string h, int offset) =>
        Convert.ToByte(string.Concat(h[offset], h[offset]), 16);

    private static byte ParseHex(string h, int offset) =>
        Convert.ToByte(h.Substring(offset, 2), 16);
}

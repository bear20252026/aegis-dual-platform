namespace Aegis.Windows.Core.Tests;

using System.Windows;
using Xunit;

/// <summary>C13 批（审计 2026-09-26）：独立窗口纯函数面直测——历史 host 提取
/// （CS-161）、书签过滤谓词（CS-165）、睡眠下拉索引（CS-169）、日历周偏移
/// （CS-176）。仅触达静态方法（无 STA 依赖）。</summary>
public sealed class WindowLogicTests
{
    // ===== CS-161：HistoryWindow.TryHost =====

    [Theory]
    [InlineData("https://example.com/x?a=1", "example.com")]
    [InlineData("http://Sub.Example.COM/", "sub.example.com")]
    [InlineData("not a url", "not a url")]      // 解析失败原样回退
    [InlineData("about:blank", "about:blank")]  // 无 host 形态原样回退
    public void TryHost_ExtractsHostOrFallsBack(string url, string expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.HistoryWindow.TryHost(url));

    // ===== CS-165：BookmarkManagerWindow.MatchesQuery =====

    [Theory]
    [InlineData("示例", "https://a.cn", "示例", true)]           // 标题命中
    [InlineData("标题甲", "https://a.cn", "a.cn", true)]         // URL 命中
    [InlineData("标题甲", "https://a.cn", "甲", true)]           // 单字命中
    [InlineData("标题甲", "https://ABC.cn/x", "abc", true)]      // 大小写不敏感（CS-162）
    [InlineData("标题甲", "https://a.cn", "zzz", false)]         // 未命中
    [InlineData("标题甲", "https://a.cn", null, true)]           // 空查询全过
    [InlineData("标题甲", "https://a.cn", "", true)]
    public void MatchesQuery_TitleOrUrlCaseInsensitive(
        string title, string url, string? query, bool expected) =>
        Assert.Equal(expected,
            Aegis.Windows.Chrome.BookmarkManagerWindow.MatchesQuery(title, url, query));

    // ===== CS-169：SettingsWindow.SleepIndex =====

    [Theory]
    [InlineData(0, 0)]
    [InlineData(15, 1)]
    [InlineData(30, 2)]   // 默认档
    [InlineData(60, 3)]
    [InlineData(99, 2)]   // 非法回退 30 分钟档
    [InlineData(-5, 2)]
    public void SleepIndex_MapsMinutesToComboIndex(int minutes, int expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.SettingsWindow.SleepIndex(minutes));

    // ===== CS-176：DateField.MondayOffset =====

    [Theory]
    [InlineData(DayOfWeek.Monday, 0)]     // 周一首列
    [InlineData(DayOfWeek.Sunday, 6)]     // 周日末列
    [InlineData(DayOfWeek.Wednesday, 2)]
    public void MondayOffset_WeekStartsMonday(DayOfWeek day, int expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.DateField.MondayOffset(day));
}

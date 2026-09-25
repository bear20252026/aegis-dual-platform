namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.ObjectModel;
using System.Threading;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Downloads;
using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Settings;
using Aegis.Windows.Core.Bookmarks;
using Xunit;

/// <summary>WPF 窗口构造冒烟测试（回归防护）：在 STA 线程实例化窗口，
/// 捕获「XAML 初始化期事件引用未初始化控件 → NullReferenceException」一类
/// 构造即崩溃的缺陷（历史窗口曾因 ChipAll IsChecked=True 触发早于控件初始化而 NRE）。
/// 任何窗口构造抛异常都会让本测试失败——防止同类问题复发。</summary>
public sealed class WindowSmokeTests
{
    [Fact]
    public void HistoryWindowConstructsAndAppliesBothThemesWithoutThrowing()
    {
        RunSta(() =>
        {
            var store = new HistoryStore(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
            var w = new HistoryWindow(store);
            // ApplyTheme 会替换资源字典值 → 触发 XAML 延迟资源的创建/解析。
            // 曾因非法颜色字面量（#FFB3FFFFFF，10 位十六进制）在此抛
            // FormatException「令牌无效」→ 历史窗口闪退。深浅各调一次锁定。
            w.ApplyTheme("dark");
            w.ApplyTheme("light");
        });
    }

    [Fact]
    public void DownloadsWindowConstructsWithoutThrowing()
    {
        RunSta(() =>
        {
            var items = new ObservableCollection<DownloadItem>();
            _ = new DownloadsWindow(items);
        });
    }

    [Fact]
    public void DateFieldConstructsAndSelectionUpdatesLabel()
    {
        RunSta(() =>
        {
            var field = new DateField();
            Assert.Null(field.SelectedDate);
            field.SelectedDate = new DateTime(2026, 9, 6);
            Assert.Equal(new DateTime(2026, 9, 6), field.SelectedDate);
            Assert.Equal("2026-09-06", field.FieldText);
        });
    }

    // ===== CS-040/041（审计 2026-09-25）：HistoryWindow 静态分支直测 =====

    [Theory]
    [InlineData("未知日期", "未知日期")]       // 分支 1：哨兵串原样透传
    [InlineData("not-a-date", "not-a-date")]   // 分支 2：非法格式原样透传
    public void HistoryWindow_DateLabel_PassthroughBranches(string input, string expected)
    {
        Assert.Equal(expected, HistoryWindow.DateLabel(input));
    }

    [Fact]
    public void HistoryWindow_DateLabel_TodayYesterdayAndWeekdayBranches()
    {
        var today = DateTime.Today;
        var yest = today.AddDays(-1);
        // 分支 3/4/5：今天 / 昨天 / 其他（星期标注）
        Assert.Multiple(
            () => Assert.Contains("今天", HistoryWindow.DateLabel(today.ToString("yyyy-MM-dd"))),
            () => Assert.Contains("昨天", HistoryWindow.DateLabel(yest.ToString("yyyy-MM-dd"))),
            () => Assert.Contains("月", HistoryWindow.DateLabel(today.AddDays(-2).ToString("yyyy-MM-dd"))));
    }

    [Fact]
    public void HistoryWindow_ParseLocalTime_CoversAllBranches()
    {
        // 合法 ISO → HH:mm 本地时刻
        var parsed = HistoryWindow.ParseLocalTime("2026-09-25T08:30:00Z");
        Assert.Matches(@"^\d{2}:\d{2}$", parsed);
        // 非法但长度足够 → 截取 11..16 的 HH:mm 片段（99 月使 TryParse 失败）
        Assert.Equal("08:30", HistoryWindow.ParseLocalTime("9999-99-99T08:30:99"));
        // 过短 → 空串
        Assert.Equal(string.Empty, HistoryWindow.ParseLocalTime("short"));
    }

    // ===== CS-059..061（审计 2026-09-25）：三个窗口 STA 构造冒烟补齐 =====

    [Fact]
    public void SettingsWindowConstructsAndAppliesBothThemesWithoutThrowing()
    {
        RunSta(() =>
        {
            var settings = AppSettings.Load(Path.Combine(Path.GetTempPath(), $"no_such_{Guid.NewGuid():N}.json"));
            var broker = new Aegis.Windows.Broker.BrowserPolicyBroker();
            var settingsService = new SettingsService(
                Path.Combine(Path.GetTempPath(), $"aegis_set_{Guid.NewGuid():N}.json"));
            // owner 仅保存时回调使用——构造期传 null 不触发解引用
            var w = new SettingsWindow(settings, broker, null!, settingsService);
            w.ApplyTheme("dark");
            w.ApplyTheme("light");
        });
    }

    [Fact]
    public void BookmarkManagerWindowConstructsAndAppliesBothThemesWithoutThrowing()
    {
        RunSta(() =>
        {
            var store = new BookmarkStore(Path.Combine(Path.GetTempPath(), $"aegis_bms_{Guid.NewGuid():N}.db"));
            var w = new BookmarkManagerWindow(store, owner: null);
            w.ApplyTheme("dark");
            w.ApplyTheme("light");
        });
    }

    [Fact]
    public void SourceViewerWindowConstructsAndAppliesBothThemesWithoutThrowing()
    {
        RunSta(() =>
        {
            var w = new SourceViewerWindow("https://example.com", "<html><body>ok</body></html>");
            w.ApplyTheme("dark");
            w.ApplyTheme("light");
        });
    }

    private static void RunSta(Action action)
    {
        Exception? caught = null;
        var thread = new Thread(() =>
        {
            try
            {
                action();
            }
            catch (Exception ex)
            {
                caught = ex;
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        Assert.Null(caught);  // 构造抛异常 → 回归失败
    }
}

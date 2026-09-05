namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using Aegis.Windows.Core.History;

/// <summary>历史记录窗口（精细化版）：支持文本搜索、快捷日期（今天/昨天/近7天/本月）、
/// 可展开日历按某天查询、起止日期范围查询；按日期分组（日期+星期+条数）、
/// 条目含时刻/标题/域名/悬停删除；跟随深浅主题。数据层全部参数绑定。</summary>
public partial class HistoryWindow : Window
{
    private readonly HistoryStore _history;
    private readonly HistoryTemplateSelector _selector;
    private bool _suppressFilter;

    public HistoryWindow(HistoryStore history)
    {
        InitializeComponent();
        _history = history;
        _selector = new HistoryTemplateSelector(
            (DataTemplate)Resources["DayHeaderTemplate"],
            (DataTemplate)Resources["HistoryRowTemplate"]);
        HistoryList.ItemTemplateSelector = _selector;
        Loaded += (_, _) =>
        {
            try
            {
                RefreshDateFilter();
                ApplyFilter();
            }
            catch (Exception ex)
            {
                Aegis.Windows.Core.Security.SecurityLog.Write(
                    $"[history] 加载历史窗口异常（已兜底）: {ex.GetType().Name}: {ex.Message}");
                EmptyHint.Text = "历史记录加载失败，请稍后重试。";
            }
        };
    }

    /// <summary>主窗口主题联动（同步 self-contained 色刷）。</summary>
    public void ApplyTheme(string? theme)
    {
        var light = string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        Resources["ChromeBackgroundBrush"] = Brush(light ? "#FFF1F3F4" : "#FF101827");
        Resources["SurfaceBrush"] = Brush(light ? "#FFFFFFFF" : "#FF1B2537");
        Resources["CardBrush"] = Brush(light ? "#FFFFFFFF" : "#FF1F2A3D");
        Resources["CardHoverBrush"] = Brush(light ? "#FFE8EAED" : "#FF2A3A55");
        Resources["TextPrimaryBrush"] = Brush(light ? "#FF1A1A1A" : "#FFFFFFFF");
        Resources["TextSecondaryBrush"] = Brush(light ? "#FF5F6368" : "#FFB3FFFFFF");
        Resources["TextMutedBrush"] = Brush(light ? "#FF80868B" : "#FF8A93A6");
        Resources["FieldBackgroundBrush"] = Brush(light ? "#FFFFFFFF" : "#FF1B2537");
        Resources["FieldBorderBrush"] = Brush(light ? "#FFDADCE0" : "#FF2E3B55");
        Resources["AccentSoftBrush"] = Brush(light ? "#1A0B57D0" : "#223B82F6");
    }

    private static System.Windows.Media.Brush Brush(string hex)
    {
        var h = hex.TrimStart('#');
        byte a = 0xFF, r, g, b;
        if (h.Length == 8)
        {
            a = Convert.ToByte(h.Substring(0, 2), 16);
            r = Convert.ToByte(h.Substring(2, 2), 16);
            g = Convert.ToByte(h.Substring(4, 2), 16);
            b = Convert.ToByte(h.Substring(6, 2), 16);
        }
        else
        {
            r = Convert.ToByte(h.Substring(0, 2), 16);
            g = Convert.ToByte(h.Substring(2, 2), 16);
            b = Convert.ToByte(h.Substring(4, 2), 16);
        }
        var brush = new System.Windows.Media.SolidColorBrush(
            System.Windows.Media.Color.FromArgb(a, r, g, b));
        brush.Freeze();
        return brush;
    }

    private void RefreshDateFilter()
    {
        // 快捷芯片初始态：全部选中；范围面板收起
        RangePanel.Visibility = Visibility.Collapsed;
    }

    // ============ 日期/搜索筛选 ============

    private void ApplyFilter()
    {
        string? from;
        string? to;
        _suppressFilter = true;
        try
        {
            ComputeRange(out from, out to);
        }
        finally
        {
            _suppressFilter = false;
        }
        Reload(SearchBox.Text, from, to);
    }

    /// <summary>由当前激活的筛选控件计算日期区间（yyyy-MM-dd，可为空）。</summary>
    private void ComputeRange(out string? from, out string? to)
    {
        var today = DateTime.Today;
        if (ChipToday.IsChecked == true)
        {
            from = today.ToString("yyyy-MM-dd");
            to = today.ToString("yyyy-MM-dd");
        }
        else if (ChipYesterday.IsChecked == true)
        {
            var y = today.AddDays(-1);
            from = y.ToString("yyyy-MM-dd");
            to = y.ToString("yyyy-MM-dd");
        }
        else if (ChipWeek.IsChecked == true)
        {
            from = today.AddDays(-6).ToString("yyyy-MM-dd");
            to = today.ToString("yyyy-MM-dd");
        }
        else if (ChipMonth.IsChecked == true)
        {
            from = new DateTime(today.Year, today.Month, 1).ToString("yyyy-MM-dd");
            to = today.ToString("yyyy-MM-dd");
        }
        else if (ChipRange.IsChecked == true)
        {
            RangePanel.Visibility = Visibility.Visible;
            from = RangeFrom.SelectedDate?.ToString("yyyy-MM-dd");
            to = RangeTo.SelectedDate?.ToString("yyyy-MM-dd");
        }
        else if (CustomDate.SelectedDate is { } d)
        {
            from = d.ToString("yyyy-MM-dd");
            to = d.ToString("yyyy-MM-dd");
        }
        else
        {
            from = null;
            to = null;
        }
    }

    private void Reload(string query, string? from, string? to)
    {
        var entries = _history.SearchRange(query, from, to, 1000);
        var items = BuildGrouped(entries);
        HistoryList.ItemsSource = items;
        var rowCount = entries.Count;
        var dayCount = entries.Select(e => e.VisitedDate).Where(d => !string.IsNullOrEmpty(d)).Distinct().Count();
        SummaryText.Text = $"{rowCount} 条 · {dayCount} 天";
        EmptyHint.Visibility = rowCount == 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyHint.Text = "没有匹配的历史记录。";
    }

    /// <summary>按日期倒序预分组：每条为「日期头 + 若干条目」，日期头含星期与条数。</summary>
    private static List<object> BuildGrouped(IReadOnlyList<HistoryEntry> entries)
    {
        var list = new List<object>();
        string? currentDay = null;
        var dayItems = new List<HistoryRow>();
        void Flush()
        {
            if (currentDay is not null && dayItems.Count > 0)
            {
                list.Add(MakeHeader(currentDay, dayItems.Count));
                list.AddRange(dayItems);
                dayItems.Clear();
            }
        }
        foreach (var e in entries)
        {
            var day = string.IsNullOrEmpty(e.VisitedDate) ? "未知日期" : e.VisitedDate;
            if (day != currentDay)
            {
                Flush();
                currentDay = day;
            }
            dayItems.Add(ToRow(e));
        }
        Flush();
        return list;
    }

    private static DayHeader MakeHeader(string date, int count)
    {
        var display = date;
        var weekday = "";
        if (DateTime.TryParseExact(date, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var d))
        {
            display = $"{d.Month}月{d.Day}日";
            weekday = WeekdayName(d.DayOfWeek);
        }
        return new DayHeader(date, display, weekday, $"{count} 条");
    }

    private static string WeekdayName(DayOfWeek d) => d switch
    {
        DayOfWeek.Monday => "星期一",
        DayOfWeek.Tuesday => "星期二",
        DayOfWeek.Wednesday => "星期三",
        DayOfWeek.Thursday => "星期四",
        DayOfWeek.Friday => "星期五",
        DayOfWeek.Saturday => "星期六",
        _ => "星期日",
    };

    private static HistoryRow ToRow(HistoryEntry e) => new(
        e.Id,
        string.IsNullOrWhiteSpace(e.Title) ? e.Url : e.Title,
        TryHost(e.Url),
        ParseLocalTime(e.VisitedAt));

    private static string ParseLocalTime(string iso)
    {
        if (DateTimeOffset.TryParse(iso, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeLocal, out var dto))
            return dto.ToLocalTime().ToString("HH:mm");
        return iso.Length >= 16 ? iso.Substring(11, 5) : string.Empty;
    }

    private static string TryHost(string url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var uri) && !string.IsNullOrEmpty(uri.Host)
            ? uri.Host
            : url;

    // ============ 事件 ============

    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
        ApplyFilter();
    }

    private void ChipFilter_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressFilter || sender is not ToggleButton tb)
            return;
        if (!(tb.IsChecked == true))
            return;
        // 芯片互斥：勾选一个，取消其它；自定义日期清空
        _suppressFilter = true;
        foreach (var chip in new[] { ChipAll, ChipToday, ChipYesterday, ChipWeek, ChipMonth, ChipRange })
        {
            if (!ReferenceEquals(chip, tb))
                chip.IsChecked = false;
        }
        CustomDate.SelectedDate = null;
        if (ReferenceEquals(tb, ChipRange))
            RangePanel.Visibility = Visibility.Visible;
        else
            RangePanel.Visibility = Visibility.Collapsed;
        _suppressFilter = false;
        ApplyFilter();
    }

    private void CustomDate_SelectedDateChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_suppressFilter)
            return;
        // 选择自定义日期：取消所有快捷芯片
        _suppressFilter = true;
        foreach (var chip in new[] { ChipAll, ChipToday, ChipYesterday, ChipWeek, ChipMonth, ChipRange })
            chip.IsChecked = false;
        RangePanel.Visibility = Visibility.Collapsed;
        _suppressFilter = false;
        ApplyFilter();
    }

    private void RangeDate_Changed(object sender, SelectionChangedEventArgs e) => ApplyFilter();

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not FrameworkElement fe)
            return;
        long id = 0;
        if (fe.Tag is long tag)
            id = tag;
        else if (fe.DataContext is HistoryRow row)
            id = row.Id;
        if (id <= 0)
            return;
        _history.Delete(id);
        ApplyFilter();
    }

    private void Clear_Click(object sender, RoutedEventArgs e)
    {
        var confirmed = MessageBox.Show(
            this,
            $"将清除全部历史记录（{(_history.Recent(1).Count > 0 ? "不可恢复" : "暂无记录")}）。确定继续？",
            "清除历史",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (confirmed != MessageBoxResult.Yes)
            return;
        _history.Clear();
        Reload("", null, null);
        MessageBox.Show(this, "历史记录已清空。", "完成", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    // ============ 模型 ============

    /// <summary>日期分组头模型。</summary>
    public sealed record DayHeader(string Date, string DisplayDate, string Weekday, string CountText);

    /// <summary>单条历史模型。</summary>
    public sealed record HistoryRow(long Id, string Title, string Host, string TimeText);

    /// <summary>根据项类型选择模板：日期头 / 单条。</summary>
    public sealed class HistoryTemplateSelector : DataTemplateSelector
    {
        private readonly DataTemplate _dayHeader;
        private readonly DataTemplate _row;

        public HistoryTemplateSelector(DataTemplate dayHeader, DataTemplate row)
        {
            _dayHeader = dayHeader;
            _row = row;
        }

        public override DataTemplate? SelectTemplate(object item, DependencyObject container) =>
            item is DayHeader ? _dayHeader : _row;
    }
}
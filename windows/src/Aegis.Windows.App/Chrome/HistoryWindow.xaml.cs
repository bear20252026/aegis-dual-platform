namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using Aegis.Windows.Core.History;

/// <summary>历史记录窗口（Apple 风格精细化版）：
/// - 查询：文本搜索 + 快捷日期分段（全部/今天/昨天/近7天/本月）+ 可展开日历选某天 + 起止范围；
/// - 展示：iOS 分组列表（「今天/昨天/9月4日」小节头 + 圆角卡片 + 发丝分隔线），
///   条目含时刻/标题/域名/删除；外层 ListBox 虚拟化 + 分页加载，千条数据流畅；
/// - 数据层全部参数绑定（安全约束）；主题跟随主窗口深浅。</summary>
public partial class HistoryWindow : Window
{
    private readonly HistoryStore _history;
    private bool _suppressFilter;
    private bool _initialized;
    private int _limit = 200;

    public HistoryWindow(HistoryStore history)
    {
        InitializeComponent();
        _history = history;
        _initialized = true;  // 此后控件事件才处理（初始化期事件一律忽略——防 NRE）
        Loaded += (_, _) =>
        {
            try
            {
                ApplyFilter();
            }
            catch (Exception ex)
            {
                Aegis.Windows.Core.Security.SecurityLog.Write(
                    $"[history] 加载历史窗口异常（已兜底）: {ex.GetType().Name}: {ex.Message}{Environment.NewLine}{ex}");
                EmptyHint.Text = "历史记录加载失败，请稍后重试。";
            }
        };
    }

    /// <summary>主窗口主题联动（iOS 深浅色板）。</summary>
    public void ApplyTheme(string? theme)
    {
        var light = string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        Resources["ChromeBackgroundBrush"] = Brush(light ? "#FFF2F2F7" : "#FF1C1C1E");
        Resources["CardBrush"] = Brush(light ? "#FFFFFFFF" : "#FF2C2C2E");
        Resources["SeparatorBrush"] = Brush(light ? "#FFE5E5EA" : "#FF38383A");
        Resources["SegmentedBrush"] = Brush(light ? "#FFE9E9EB" : "#FF2C2C2E");
        Resources["SegmentedSelectedBrush"] = Brush(light ? "#FFFFFFFF" : "#FF5A5A5E");
        Resources["FieldBackgroundBrush"] = Brush(light ? "#FFE9E9EB" : "#FF2C2C2E");
        Resources["TextPrimaryBrush"] = Brush(light ? "#FF1A1A1A" : "#FFFFFFFF");
        Resources["TextSecondaryBrush"] = Brush(light ? "#FF8A8A8E" : "#FF98989F");
        Resources["TextMutedBrush"] = Brush(light ? "#FFAEAEB2" : "#FF6C6C70");
        Resources["AccentBrush"] = Brush(light ? "#FF007AFF" : "#FF0A84FF");
        Resources["AccentSoftBrush"] = Brush(light ? "#1A007AFF" : "#220A84FF");
    }

    private static System.Windows.Media.Brush Brush(string hex)
    {
        // 手动解析 #AARRGGBB / #RRGGBB——规避 ColorConverter 运行时「Invalid token」异常
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

    // ============ 筛选 ============

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
        try
        {
            Reload(SearchBox.Text, from, to);
        }
        catch (Exception ex)
        {
            Aegis.Windows.Core.Security.SecurityLog.Write(
                $"[history] 筛选异常（已兜底）: {ex.GetType().Name}: {ex.Message}");
            EmptyHint.Text = "查询失败，请调整筛选条件后重试。";
        }
    }

    /// <summary>由激活的筛选控件计算日期区间（yyyy-MM-dd，空=不限）。</summary>
    private void ComputeRange(out string? from, out string? to)
    {
        var today = DateTime.Today;
        from = null;
        to = null;
        if (ChipToday.IsChecked == true)
        {
            from = to = today.ToString("yyyy-MM-dd");
        }
        else if (ChipYesterday.IsChecked == true)
        {
            var y = today.AddDays(-1);
            from = to = y.ToString("yyyy-MM-dd");
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
            from = to = d.ToString("yyyy-MM-dd");
        }
    }

    private void Reload(string query, string? from, string? to)
    {
        var entries = _history.SearchRange(query, from, to, _limit);
        var groups = BuildGroups(entries);
        HistoryList.ItemsSource = groups;
        var dayCount = groups.Count;
        SummaryText.Text = $"{entries.Count} 条 · {dayCount} 天";
        EmptyHint.Visibility = entries.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyHint.Text = "没有匹配的历史记录。";
        LoadMoreButton.Visibility = entries.Count >= _limit ? Visibility.Visible : Visibility.Collapsed;
    }

    /// <summary>按日期倒序分组：日期标签（今天/昨天/9月4日 星期五）+ 该日条目。</summary>
    private static List<DayGroup> BuildGroups(IReadOnlyList<HistoryEntry> entries)
    {
        var groups = new List<DayGroup>();
        var byDay = entries
            .GroupBy(e => string.IsNullOrEmpty(e.VisitedDate) ? "未知日期" : e.VisitedDate)
            .OrderByDescending(g => g.Key, StringComparer.Ordinal);
        foreach (var g in byDay)
        {
            var date = g.Key;
            groups.Add(new DayGroup(
                DateLabel(date),
                g.Select(e => new HistoryRow(
                    e.Id,
                    string.IsNullOrWhiteSpace(e.Title) ? e.Url : e.Title,
                    TryHost(e.Url),
                    ParseLocalTime(e.VisitedAt))).ToList()));
        }
        return groups;
    }

    /// <summary>iOS 风格日期标签：今天 / 昨天 / 9月4日 星期五 / 未知日期。</summary>
    private static string DateLabel(string date)
    {
        if (date == "未知日期")
            return date;
        if (!DateTime.TryParseExact(date, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var d))
            return date;
        var today = DateTime.Today;
        if (d == today)
            return $"今天 · {d.Month}月{d.Day}日";
        if (d == today.AddDays(-1))
            return $"昨天 · {d.Month}月{d.Day}日";
        return $"{d.Month}月{d.Day}日 {Weekday(d.DayOfWeek)}";
    }

    private static string Weekday(DayOfWeek d) => d switch
    {
        DayOfWeek.Monday => "星期一",
        DayOfWeek.Tuesday => "星期二",
        DayOfWeek.Wednesday => "星期三",
        DayOfWeek.Thursday => "星期四",
        DayOfWeek.Friday => "星期五",
        DayOfWeek.Saturday => "星期六",
        _ => "星期日",
    };

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
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Collapsed : Visibility.Visible;
        ApplyFilter();
    }

    private void ChipFilter_Changed(object sender, RoutedEventArgs e)
    {
        if (!_initialized || _suppressFilter || sender is not ToggleButton tb)
            return;
        if (!(tb.IsChecked == true))
            return;
        _suppressFilter = true;
        foreach (var chip in new[] { ChipAll, ChipToday, ChipYesterday, ChipWeek, ChipMonth, ChipRange })
        {
            if (!ReferenceEquals(chip, tb))
                chip.IsChecked = false;
        }
        CustomDate.SelectedDate = null;
        RangePanel.Visibility = ReferenceEquals(tb, ChipRange) ? Visibility.Visible : Visibility.Collapsed;
        _suppressFilter = false;
        ApplyFilter();
    }

    private void CustomDate_SelectedDateChanged(object sender, EventArgs e)
    {
        if (!_initialized || _suppressFilter)
            return;
        _suppressFilter = true;
        foreach (var chip in new[] { ChipAll, ChipToday, ChipYesterday, ChipWeek, ChipMonth, ChipRange })
            chip.IsChecked = false;
        RangePanel.Visibility = Visibility.Collapsed;
        _suppressFilter = false;
        ApplyFilter();
    }

    private void RangeDate_Changed(object sender, EventArgs e)
    {
        if (!_initialized)
            return;
        ApplyFilter();
    }

    private void LoadMore_Click(object sender, RoutedEventArgs e)
    {
        _limit += 300;
        ApplyFilter();
    }

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (!_initialized || sender is not FrameworkElement fe)
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
        if (!_initialized)
            return;
        var confirmed = MessageBox.Show(
            this,
            "将清除全部历史记录（不可恢复）。确定继续？",
            "清除历史",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (confirmed != MessageBoxResult.Yes)
            return;
        _history.Clear();
        _limit = 200;
        ApplyFilter();
        MessageBox.Show(this, "历史记录已清空。", "完成", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    // ============ 模型 ============

    /// <summary>关闭时释放列表引用（内存卫生——尽快让分组/行模型可回收）。</summary>
    protected override void OnClosed(EventArgs e)
    {
        HistoryList.ItemsSource = null;
        base.OnClosed(e);
    }

    /// <summary>日期分组（iOS 分组列表的一节）。</summary>
    public sealed record DayGroup(string DateLabel, IReadOnlyList<HistoryRow> Rows);

    /// <summary>单条历史模型。</summary>
    public sealed record HistoryRow(long Id, string Title, string Host, string TimeText);
}
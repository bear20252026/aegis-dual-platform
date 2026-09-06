namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using Aegis.Windows.Core.History;

/// <summary>历史记录窗口（Java 风格）：游标分页加载——首屏只拉一页，滚动触底/点
/// 「加载更多」按游标追加下一页（不重建已有项），减轻长历史的加载与内存负担。
/// 分组按日期合并；搜索/日期/删除/清空重置游标重新拉首页。数据层全部参数绑定。</summary>
public partial class HistoryWindow : Window
{
    private const int PageSize = 100;
    private readonly HistoryStore _history;
    private readonly ObservableCollection<DayGroup> _groups = new();
    private PageCursor? _pageCursor;
    private bool _hasMore = true;
    private bool _loading;
    private bool _suppressFilter;
    private bool _initialized;

    public HistoryWindow(HistoryStore history)
    {
        InitializeComponent();
        _history = history;
        HistoryList.ItemsSource = _groups;
        // 滚动触底自动加载下一页（ListBox 内部 ScrollViewer 以路由事件冒泡）
        HistoryList.AddHandler(
            ScrollViewer.ScrollChangedEvent,
            (ScrollChangedEventHandler)HistoryScroller_ScrollChanged);
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

    // ============ 筛选（重置游标 → 拉首页） ============

    private void ApplyFilter()
    {
        string? from;
        string? to;
        _suppressFilter = true;
        try { ComputeRange(out from, out to); }
        finally { _suppressFilter = false; }
        ResetAndLoad(SearchBox.Text, from, to);
    }

    private void ComputeRange(out string? from, out string? to)
    {
        var today = DateTime.Today;
        from = null;
        to = null;
        if (ChipToday.IsChecked == true) { from = to = today.ToString("yyyy-MM-dd"); }
        else if (ChipYesterday.IsChecked == true) { var y = today.AddDays(-1); from = to = y.ToString("yyyy-MM-dd"); }
        else if (ChipWeek.IsChecked == true) { from = today.AddDays(-6).ToString("yyyy-MM-dd"); to = today.ToString("yyyy-MM-dd"); }
        else if (ChipMonth.IsChecked == true) { from = new DateTime(today.Year, today.Month, 1).ToString("yyyy-MM-dd"); to = today.ToString("yyyy-MM-dd"); }
        else if (ChipRange.IsChecked == true) { RangePanel.Visibility = Visibility.Visible; from = RangeFrom.SelectedDate?.ToString("yyyy-MM-dd"); to = RangeTo.SelectedDate?.ToString("yyyy-MM-dd"); }
        else if (CustomDate.SelectedDate is { } d) { from = to = d.ToString("yyyy-MM-dd"); }
    }

    /// <summary>重置分页并加载第一页（筛选/删除/清空后调用）。</summary>
    private void ResetAndLoad(string query, string? from, string? to)
    {
        _groups.Clear();
        _pageCursor = null;
        _hasMore = true;
        _loading = false;
        LoadNextPage(query, from, to);
    }

    /// <summary>用游标拉取并追加下一页（滚动触底/加载更多）。</summary>
    private void LoadNextPage(string query, string? from, string? to)
    {
        if (_loading || !_hasMore)
            return;
        _loading = true;
        try
        {
            var page = _history.SearchRangePaged(query, from, to, PageSize, _pageCursor);
            MergeIntoGroups(page.Entries);
            _pageCursor = page.NextCursor;
            _hasMore = page.HasMore;
            var total = _groups.Sum(g => g.Rows.Count);
            SummaryText.Text = $"已加载 {total} 条";
            EmptyHint.Visibility = total == 0 ? Visibility.Visible : Visibility.Collapsed;
            EmptyHint.Text = "没有匹配的历史记录。";
            LoadMoreButton.Visibility = _hasMore ? Visibility.Visible : Visibility.Collapsed;
        }
        catch (Exception ex)
        {
            Aegis.Windows.Core.Security.SecurityLog.Write(
                $"[history] 分页加载异常（已兜底）: {ex.GetType().Name}: {ex.Message}");
            EmptyHint.Text = "查询失败，请调整筛选条件后重试。";
        }
        finally
        {
            _loading = false;
        }
    }

    /// <summary>把新页条目合并进已有日期分组：同日期并入现有组，新日期新建组（按日期倒序）。
    /// 页内按 (visited_at,id) 倒序、日期连续非增，故可顺序合并。</summary>
    private void MergeIntoGroups(IReadOnlyList<HistoryEntry> entries)
    {
        var index = _groups.Count - 1;  // 从最后一组开始（新页日期不早于已加载）
        foreach (var e in entries)
        {
            var day = string.IsNullOrEmpty(e.VisitedDate) ? "未知日期" : e.VisitedDate;
            var row = new HistoryRow(
                e.Id,
                string.IsNullOrWhiteSpace(e.Title) ? e.Url : e.Title,
                TryHost(e.Url),
                ParseLocalTime(e.VisitedAt));
            if (index >= 0 && _groups[index].Date == day)
            {
                _groups[index].Rows.Add(row);
            }
            else
            {
                var group = new DayGroup(day, DateLabel(day));
                group.Rows.Add(row);
                index++;
                _groups.Insert(index, group);
            }
        }
    }

    private static string DateLabel(string date)
    {
        if (date == "未知日期")
            return date;
        if (!DateTime.TryParseExact(date, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var d))
            return date;
        var today = DateTime.Today;
        if (d == today) return $"今天 · {d.Month}月{d.Day}日";
        if (d == today.AddDays(-1)) return $"昨天 · {d.Month}月{d.Day}日";
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
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
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
            if (!ReferenceEquals(chip, tb))
                chip.IsChecked = false;
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
        string? from; string? to;
        ComputeRange(out from, out to);
        LoadNextPage(SearchBox.Text, from, to);
    }

    /// <summary>滚动接近底部自动加载下一页。</summary>
    private void HistoryScroller_ScrollChanged(object sender, ScrollChangedEventArgs e)
    {
        if (e.ExtentHeight - (e.VerticalOffset + e.ViewportHeight) < 120)
            LoadMore_Click(sender, e);
    }

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (!_initialized || sender is not FrameworkElement fe)
            return;
        long id = 0;
        if (fe.Tag is long tag) id = tag;
        else if (fe.DataContext is HistoryRow row) id = row.Id;
        if (id <= 0) return;
        _history.Delete(id);
        ApplyFilter();
    }

    private void Clear_Click(object sender, RoutedEventArgs e)
    {
        if (!_initialized)
            return;
        var confirmed = MessageBox.Show(this, "将清除全部历史记录（不可恢复）。确定继续？",
            "清除历史", MessageBoxButton.YesNo, MessageBoxImage.Warning);
        if (confirmed != MessageBoxResult.Yes)
            return;
        _history.Clear();
        ApplyFilter();
        MessageBox.Show(this, "历史记录已清空。", "完成", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    // ============ 模型 ============

    /// <summary>关闭时释放列表引用（内存卫生）。</summary>
    protected override void OnClosed(EventArgs e)
    {
        _groups.Clear();
        HistoryList.ItemsSource = null;
        base.OnClosed(e);
    }

    /// <summary>日期分组（可变——分页追加时并入 Rows）。</summary>
    public sealed class DayGroup
    {
        public DayGroup(string date, string dateLabel)
        {
            Date = date;
            DateLabel = dateLabel;
        }

        public string Date { get; }

        public string DateLabel { get; }

        public ObservableCollection<HistoryRow> Rows { get; } = new();
    }

    public sealed record HistoryRow(long Id, string Title, string Host, string TimeText);
}
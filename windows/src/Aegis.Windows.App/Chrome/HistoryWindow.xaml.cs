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

/// <summary>历史记录窗口（页码式分页）。列表为**扁平虚拟化列表**——日期变化处
/// 内嵌一个「日期头」行（同日期多条也只是连续行，逐行虚拟化 → 单日再多也能
/// 滚动，修复「组内不可滚动」）。底部页码条 + 每页条数设置。数据层参数绑定。</summary>
public partial class HistoryWindow : Window
{
    private int _pageSize = 100;
    private int _currentPage = 1;
    private int _totalPages;
    private long _totalCount;
    private readonly HistoryStore _history;
    private readonly ObservableCollection<object> _items = new();
    private readonly HistoryItemSelector _selector;
    private bool _suppressFilter;
    private bool _initialized;

    public HistoryWindow(HistoryStore history)
    {
        InitializeComponent();
        _history = history;
        _selector = new HistoryItemSelector(
            (DataTemplate)Resources["DateHeaderTemplate"],
            (DataTemplate)Resources["HistoryRowTemplate"]);
        HistoryList.ItemsSource = _items;
        HistoryList.ItemTemplateSelector = _selector;
        _initialized = true;  // 此后控件事件才处理（初始化期事件一律忽略——防 NRE）
        Loaded += (_, _) =>
        {
            try { ApplyFilter(); }
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

    private static System.Windows.Media.Brush Brush(string hex) =>
        Core.ThemeColor.ParseBrush(hex);

    // ============ 筛选 ============

    private void ApplyFilter()
    {
        string? from;
        string? to;
        _suppressFilter = true;
        try { ComputeRange(out from, out to); }
        finally { _suppressFilter = false; }
        LoadPage(1);
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

    /// <summary>按页加载：只查询当前页，页码跳转不累积内存。</summary>
    private void LoadPage(int page)
    {
        if (!_initialized || page < 1)
            return;
        string? from; string? to;
        ComputeRange(out from, out to);
        _totalCount = _history.Count(SearchBox.Text, from, to);
        _totalPages = Math.Max(1, (int)Math.Ceiling(_totalCount / (double)_pageSize));
        _currentPage = Math.Min(page, _totalPages);
        var entries = _history.SearchRangePage(SearchBox.Text, from, to, _pageSize,
            (_currentPage - 1) * _pageSize);
        _items.Clear();
        string? lastDay = null;
        foreach (var e in entries)
        {
            var day = string.IsNullOrEmpty(e.VisitedDate) ? "未知日期" : e.VisitedDate;
            if (day != lastDay)
            {
                _items.Add(new DateHeader(day));
                lastDay = day;
            }
            _items.Add(new HistoryRow(e.Id,
                string.IsNullOrWhiteSpace(e.Title) ? e.Url : e.Title,
                TryHost(e.Url),
                ParseLocalTime(e.VisitedAt)));
        }
        SummaryText.Text = $"共 {_totalCount} 条 · 第 {_currentPage} / {_totalPages} 页";
        EmptyHint.Visibility = _totalCount == 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyHint.Text = "没有匹配的历史记录。";
        RenderPagination();
    }

    private void RenderPagination()
    {
        PageButtons.Items.Clear();
        var first = Math.Max(1, _currentPage - 2);
        var last = Math.Min(_totalPages, first + 4);
        if (last - first < 4) first = Math.Max(1, last - 4);
        for (var i = first; i <= last; i++)
        {
            var page = new Button { Content = i.ToString(), Tag = i, Style = (Style)FindResource("PageButton") };
            page.Click += Page_Click;
            PageButtons.Items.Add(page);
        }
        PrevPageButton.IsEnabled = _currentPage > 1;
        NextPageButton.IsEnabled = _currentPage < _totalPages;
        PageStatus.Text = $"第 {_currentPage} / {_totalPages} 页";
    }

    private void Page_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: int page }) LoadPage(page);
    }

    private void PrevPage_Click(object sender, RoutedEventArgs e) => LoadPage(_currentPage - 1);
    private void NextPage_Click(object sender, RoutedEventArgs e) => LoadPage(_currentPage + 1);
    private void PageSize_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (!_initialized || PageSizeBox.SelectedItem is not ComboBoxItem item
            || item.Tag is not string value || !int.TryParse(value, out var size))
            return;
        _pageSize = size;
        LoadPage(1);
    }

    // ============ 日期标签 ============

    internal static string DateLabel(string date)
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

    protected override void OnClosed(EventArgs e)
    {
        _items.Clear();
        HistoryList.ItemsSource = null;
        base.OnClosed(e);
    }

    /// <summary>内嵌日期头行（占一行——保证列表逐行虚拟化可滚动）。</summary>
    public sealed class DateHeader
    {
        public DateHeader(string day) => Day = day;
        public string Day { get; }
        public string Label => DateLabel(Day);
    }

    public sealed record HistoryRow(long Id, string Title, string Host, string TimeText);

    /// <summary>按项类型选模板：日期头 / 历史行。</summary>
    public sealed class HistoryItemSelector : DataTemplateSelector
    {
        private readonly DataTemplate _header;
        private readonly DataTemplate _row;

        public HistoryItemSelector(DataTemplate header, DataTemplate row)
        {
            _header = header;
            _row = row;
        }

        public override DataTemplate? SelectTemplate(object item, DependencyObject container) =>
            item is DateHeader ? _header : _row;
    }
}
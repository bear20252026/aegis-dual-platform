namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using Aegis.Windows.Core.History;

/// <summary>历史记录窗口（升级版）：保存每次访问的本地日期+时刻；支持文本搜索 /
/// 按日期筛选 / 单条删除 / 清空；按日期分组倒序展示。
/// 渲染用「预分组列表 + DataTemplateSelector」，避免 CollectionViewSource 分组在
/// 渲染期触发的 FormatException（曾导致历史窗口闪退），数据层全部参数绑定。</summary>
public partial class HistoryWindow : Window
{
    private readonly HistoryStore _history;
    private readonly HistoryTemplateSelector _selector;

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
                Reload(SearchBox.Text, SelectedDate());
            }
            catch (Exception ex)
            {
                Aegis.Windows.Core.Security.SecurityLog.Write(
                    $"[history] 加载历史窗口异常（已兜底）: {ex.GetType().Name}: {ex.Message}");
                EmptyHint.Text = "历史记录加载失败，请稍后重试。";
                HistoryList.ItemsSource = null;
            }
        };
    }

    /// <summary>主窗口主题联动（同步 self-contained 色刷）。</summary>
    public void ApplyTheme(string? theme)
    {
        var light = string.Equals(theme, "light", StringComparison.OrdinalIgnoreCase);
        Resources["ChromeBackgroundBrush"] = Brush(light ? "#FFF1F3F4" : "#FF101827");
        Resources["CardBrush"] = Brush(light ? "#FFE8EAED" : "#1FFFFFFF");
        Resources["TextPrimaryBrush"] = Brush(light ? "#FF1A1A1A" : "#FFFFFFFF");
        Resources["TextSecondaryBrush"] = Brush(light ? "#FF5F6368" : "#FFB3FFFFFF");
        Resources["TextMutedBrush"] = Brush(light ? "#FF80868B" : "#FF8A93A6");
        Resources["FieldBackgroundBrush"] = Brush(light ? "#FFFFFFFF" : "#1FFFFFFF");
        Resources["FieldBorderBrush"] = Brush(light ? "#FFDADCE0" : "#2EFFFFFF");
    }

    private static System.Windows.Media.Brush Brush(string hex)
    {
        // 手动解析 #AARRGGBB / #RRGGBB——规避 ColorConverter.ConvertFromString
        // 在个别环境下对同一合法色值抛「Invalid token」的运行时异常
        var h = hex.TrimStart('#');
        byte a = 0xFF, r, g, b;
        if (h.Length == 6)
        {
            r = HexByte(h, 0); g = HexByte(h, 2); b = HexByte(h, 4);
        }
        else if (h.Length == 8)
        {
            a = HexByte(h, 0); r = HexByte(h, 2); g = HexByte(h, 4); b = HexByte(h, 6);
        }
        else
        {
            a = 0xFF; r = 0xFF; g = 0xFF; b = 0xFF;  // 非法值回退白色，绝不抛
        }
        var brush = new System.Windows.Media.SolidColorBrush(
            System.Windows.Media.Color.FromArgb(a, r, g, b));
        brush.Freeze();
        return brush;
    }

    private static byte HexByte(string h, int offset) =>
        Convert.ToByte(h.Substring(offset, 2), 16);

    private string? SelectedDate() =>
        DateFilter.SelectedIndex <= 0 ? null : DateFilter.SelectedItem as string;

    private void RefreshDateFilter()
    {
        var dates = _history.Dates(90).ToList();
        var items = new List<object?> { "全部日期" };
        items.AddRange(dates.Cast<object>());
        DateFilter.ItemsSource = items;
        DateFilter.SelectedIndex = 0;
    }

    private void Reload(string query, string? date)
    {
        var entries = _history.Search(query, date, 1000);
        var items = BuildGrouped(entries);
        HistoryList.ItemsSource = items;
        var rowCount = entries.Count;
        var dayCount = entries.Select(e => e.VisitedDate).Where(d => !string.IsNullOrEmpty(d)).Distinct().Count();
        EmptyHint.Text = rowCount == 0
            ? "暂无匹配的历史记录。"
            : $"共 {rowCount} 条 · {dayCount} 个日期";
    }

    /// <summary>按日期倒序预分组：每条以「日期头 + 若干条目」为一组平铺（纯内存，
    /// 不依赖 CollectionViewSource 分组）。</summary>
    private static List<object> BuildGrouped(IReadOnlyList<HistoryEntry> entries)
    {
        var list = new List<object>();
        string? currentDay = null;
        var dayItems = new List<HistoryRow>();
        void Flush()
        {
            if (currentDay is not null)
            {
                list.Add(new DayHeader(currentDay, dayItems.Count, $"{dayItems.Count} 条"));
                list.AddRange(dayItems);
                dayItems.Clear();
            }
        }
        // entries 已按 visited_at 倒序 → 日期倒序
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

    private static HistoryRow ToRow(HistoryEntry e)
    {
        var timeText = ParseLocalTime(e.VisitedAt);
        var host = TryHost(e.Url);
        return new HistoryRow(
            e.Id,
            string.IsNullOrWhiteSpace(e.Title) ? e.Url : e.Title,
            e.Url,
            timeText,
            e.VisitedDate);
    }

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

    private void SearchBox_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
        Reload(SearchBox.Text, SelectedDate());
    }

    private void DateFilter_Changed(object sender, System.Windows.Controls.SelectionChangedEventArgs e) =>
        Reload(SearchBox.Text, SelectedDate());

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not System.Windows.FrameworkElement fe)
            return;
        long id = 0;
        if (fe.Tag is long tag)
            id = tag;
        else if (fe.DataContext is HistoryRow row)
            id = row.Id;
        if (id <= 0)
            return;
        _history.Delete(id);
        Reload(SearchBox.Text, SelectedDate());
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
        Reload("", null);
        RefreshDateFilter();
        MessageBox.Show(this, "历史记录已清空。", "完成", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    /// <summary>日期分组头模型。</summary>
    public sealed record DayHeader(string Date, int Count, string CountText);

    /// <summary>单条历史模型。</summary>
    public sealed record HistoryRow(long Id, string Title, string Url, string TimeText, string VisitedDate);

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
namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Data;
using Aegis.Windows.Core.History;

/// <summary>历史记录窗口（升级版）：保存每次访问的本地日期+时刻；支持
/// 文本搜索 / 按日期筛选 / 单条删除 / 清空；按日期分组、倒序精展示。
/// 数据层全部参数绑定（HistoryStore）；本类只做展示编排。</summary>
public partial class HistoryWindow : Window
{
    private readonly HistoryStore _history;

    public HistoryWindow(HistoryStore history)
    {
        InitializeComponent();
        _history = history;
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

    /// <summary>主窗口主题联动（把主窗口 9 块色刷同步到本窗口 self-contained 资源）。</summary>
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
        var c = (System.Windows.Media.Color)System.Windows.Media.ColorConverter.ConvertFromString(hex);
        var b = new System.Windows.Media.SolidColorBrush(c);
        b.Freeze();
        return b;
    }

    private string? SelectedDate() =>
        DateFilter.SelectedIndex <= 0 ? null : DateFilter.SelectedItem as string;

    private void RefreshDateFilter()
    {
        var dates = _history.Dates(90).ToList();
        var items = new List<object> { "全部日期" };
        items.AddRange(dates);
        DateFilter.ItemsSource = items;
        DateFilter.SelectedIndex = 0;
    }

    private void Reload(string query, string? date)
    {
        var entries = _history.Search(query, date, 1000);
        var rows = entries.Select(ToRow).ToList();
        var view = new ListCollectionView(rows)
        {
            SortDescriptions =
            {
                new SortDescription(nameof(HistoryRow.SortKey), ListSortDirection.Descending),
            },
        };
        view.GroupDescriptions.Add(new PropertyGroupDescription(nameof(HistoryRow.VisitedDate)));
        HistoryList.ItemsSource = view;
        var dayCount = rows.Select(r => r.VisitedDate).Where(d => !string.IsNullOrEmpty(d)).Distinct().Count();
        EmptyHint.Text = rows.Count == 0
            ? "暂无匹配的历史记录。"
            : $"共 {rows.Count} 条 · {dayCount} 个日期";
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
            e.VisitedDate,
            e.VisitedAt);  // ISO 排序键（desc 即时间倒序）
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

    /// <summary>列表行视图（分组键=VisitedDate；SortKey=ISO 倒序；TimeText=本地时刻）。</summary>
    public sealed record HistoryRow(long Id, string Title, string Url, string TimeText, string VisitedDate, string SortKey);
}
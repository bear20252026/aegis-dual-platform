namespace Aegis.Windows.Chrome;

using System;
using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Aegis.Windows.Core.Bookmarks;

/// <summary>书签管理器窗口：搜索/编辑标题/打开/删除/清空。数据层参数绑定。</summary>
public partial class BookmarkManagerWindow : Window
{
    private readonly BookmarkStore _bookmarks;
    private readonly MainWindow? _owner;
    private readonly ObservableCollection<BookmarkRow> _rows = new();

    public BookmarkManagerWindow(BookmarkStore bookmarks, MainWindow? owner = null)
    {
        InitializeComponent();
        _bookmarks = bookmarks;
        _owner = owner;
        BookmarkList.ItemsSource = _rows;
        Loaded += (_, _) => Reload("");
    }

    private void Reload(string query)
    {
        _rows.Clear();
        var q = query.Trim().ToLowerInvariant();
        foreach (var b in _bookmarks.All())
        {
            if (!string.IsNullOrEmpty(q)
                && !b.Title.ToLowerInvariant().Contains(q)
                && !b.Url.ToLowerInvariant().Contains(q))
                continue;
            _rows.Add(new BookmarkRow(b.Id, b.Title, b.Url));
        }
        BookmarkList.ItemsSource = _rows;
        SummaryText.Text = $"共 {_rows.Count} 个书签";
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
    }

    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
        Reload(SearchBox.Text);
    }

    private void Edit_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: BookmarkRow row })
        {
            EditPanel.Visibility = Visibility.Visible;
            EditTitle.Text = row.Title;
            EditUrl.Text = row.Url;
            _editingId = row.Id;
            EditTitle.Focus();
            EditTitle.SelectAll();
        }
    }

    private void EditCancel_Click(object sender, RoutedEventArgs e) =>
        EditPanel.Visibility = Visibility.Collapsed;

    private void EditSave_Click(object sender, RoutedEventArgs e)
    {
        var title = EditTitle.Text.Trim();
        if (string.IsNullOrEmpty(title) || _editingId <= 0)
            return;
        _bookmarks.Rename(_editingId, title);
        EditPanel.Visibility = Visibility.Collapsed;
        Reload(SearchBox.Text);
    }

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: BookmarkRow row })
        {
            _bookmarks.RemoveById(row.Id);
            Reload(SearchBox.Text);
        }
    }

    private void ClearAll_Click(object sender, RoutedEventArgs e)
    {
        var confirmed = MessageBox.Show(this, "将清除全部书签（不可恢复）。确定继续？",
            "清空书签", MessageBoxButton.YesNo, MessageBoxImage.Warning);
        if (confirmed != MessageBoxResult.Yes)
            return;
        _bookmarks.ClearAll();
        Reload(SearchBox.Text);
    }

    private void OpenBookmark_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: BookmarkRow row })
            _owner?.OpenInActiveTab(row.Url);
    }

    private long _editingId;

    public sealed record BookmarkRow(long Id, string Title, string Url);
}
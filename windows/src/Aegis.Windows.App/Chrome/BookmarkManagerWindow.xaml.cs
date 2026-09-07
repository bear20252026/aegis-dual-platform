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
    private const int TitleMaxLength = 256;

    private readonly BookmarkStore _bookmarks;
    private readonly MainWindow? _owner;
    private readonly ObservableCollection<BookmarkRow> _rows = new();

    public BookmarkManagerWindow(BookmarkStore bookmarks, MainWindow? owner = null)
    {
        InitializeComponent();
        _bookmarks = bookmarks;
        _owner = owner;
        BookmarkList.ItemsSource = _rows;
        BookmarkList.KeyDown += BookmarkList_KeyDown;
        Loaded += (_, _) => Reload("");
    }

    /// <summary>主窗口主题联动（浅色模式下不再永远深色）。</summary>
    public void ApplyTheme(string? theme) => WindowTheme.Apply(this, theme);

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
            OpenEditor(row);
        }
    }

    /// <summary>打开编辑弹层：同时屏蔽背后列表交互（此前无遮罩——编辑期间仍可
    /// 点列表换目标，_editingId 与面板内容错位）。</summary>
    private void OpenEditor(BookmarkRow row)
    {
        EditPanel.Visibility = Visibility.Visible;
        BookmarkList.IsHitTestVisible = false;
        EditTitle.Text = row.Title;
        EditUrl.Text = row.Url;
        _editingId = row.Id;
        EditTitle.Focus();
        EditTitle.SelectAll();
    }

    private void CloseEditor()
    {
        EditPanel.Visibility = Visibility.Collapsed;
        BookmarkList.IsHitTestVisible = true;
        _editingId = 0;
    }

    private void EditCancel_Click(object sender, RoutedEventArgs e) => CloseEditor();

    private void EditSave_Click(object sender, RoutedEventArgs e)
    {
        var title = EditTitle.Text.Trim();
        if (string.IsNullOrEmpty(title))
        {
            // 空标题不再静默 return——给用户可见反馈
            EditTitle.Focus();
            return;
        }
        if (title.Length > TitleMaxLength)
            title = title[..TitleMaxLength];
        if (_editingId > 0)
            _bookmarks.Rename(_editingId, title);
        CloseEditor();
        Reload(SearchBox.Text);
        _owner?.RefreshBookmarkBar();
    }

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: BookmarkRow row })
        {
            _bookmarks.RemoveById(row.Id);
            Reload(SearchBox.Text);
            _owner?.RefreshBookmarkBar();
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
        _owner?.RefreshBookmarkBar();
    }

    private void OpenBookmark(BookmarkRow row) => _owner?.OpenInActiveTab(row.Url);

    private void OpenBookmark_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: BookmarkRow row })
            OpenBookmark(row);
    }

    /// <summary>键盘可达：Enter 打开选中书签（此前仅鼠标点击可达）。</summary>
    private void BookmarkList_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && BookmarkList.SelectedItem is BookmarkRow row)
        {
            OpenBookmark(row);
            e.Handled = true;
        }
        else if (e.Key == Key.Delete && BookmarkList.SelectedItem is BookmarkRow del)
        {
            _bookmarks.RemoveById(del.Id);
            Reload(SearchBox.Text);
            _owner?.RefreshBookmarkBar();
            e.Handled = true;
        }
    }

    private long _editingId;

    public sealed record BookmarkRow(long Id, string Title, string Url);
}

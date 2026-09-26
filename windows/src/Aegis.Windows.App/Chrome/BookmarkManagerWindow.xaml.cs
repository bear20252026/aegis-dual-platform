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
    private System.Windows.Threading.DispatcherTimer? _searchDebounce;

    public BookmarkManagerWindow(BookmarkStore bookmarks, MainWindow? owner = null)
    {
        InitializeComponent();
        _bookmarks = bookmarks;
        _owner = owner;
        BookmarkList.ItemsSource = _rows;
        BookmarkList.KeyDown += BookmarkList_KeyDown;
        // CS-225：编辑弹层键盘路径——Enter 保存、Esc 取消（此前仅鼠标可达）
        EditTitle.KeyDown += EditorField_KeyDown;
        EditUrl.KeyDown += EditorField_KeyDown;
        Loaded += (_, _) => Reload("");
    }

    /// <summary>主窗口主题联动（浅色模式下不再永远深色）。</summary>
    public void ApplyTheme(string? theme) => WindowTheme.Apply(this, theme);

    protected override void OnClosed(EventArgs e)
    {
        // CS-032：关闭时停防抖定时器（避免 timer 持窗口引用延迟回收）
        _searchDebounce?.Stop();
        base.OnClosed(e);
    }

    /// <summary>CS-165：过滤谓词提纯直测；CS-162：OrdinalIgnoreCase 直判
    /// ——此前每行两串 ToLowerInvariant 堆分配。</summary>
    internal static bool MatchesQuery(string title, string url, string? query)
    {
        if (string.IsNullOrEmpty(query))
            return true;
        return title.Contains(query, StringComparison.OrdinalIgnoreCase)
            || url.Contains(query, StringComparison.OrdinalIgnoreCase);
    }

    private void Reload(string query)
    {
        _rows.Clear();
        var q = query.Trim();
        var all = _bookmarks.All();
        foreach (var b in all)
        {
            if (MatchesQuery(b.Title, b.Url, q))
                _rows.Add(new BookmarkRow(b.Id, b.Title, b.Url));
        }
        // CS-166：筛选态下「共 N」语义误导 → 明示 匹配 N / 共 M
        SummaryText.Text = string.IsNullOrEmpty(q)
            ? $"共 {_rows.Count} 个书签"
            : $"匹配 {_rows.Count} / 共 {all.Count} 个书签";
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
    }

    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
        // CS-032（审计 2026-09-25）：200ms 防抖——此前每键入一字符即全表加载
        //（All() 每次全量 SELECT + 过滤），长书签列表输入卡顿
        if (_searchDebounce is null)
        {
            _searchDebounce = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(200)
            };
            _searchDebounce.Tick += (_, _) =>
            {
                _searchDebounce?.Stop();
                Reload(SearchBox.Text);
            };
        }
        _searchDebounce.Stop();
        _searchDebounce.Start();
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

    private void EditorField_KeyDown(object sender, System.Windows.Input.KeyEventArgs e)
    {
        switch (e.Key)
        {
            case Key.Enter:
                EditSave_Click(sender, new RoutedEventArgs());
                e.Handled = true;
                break;
            case Key.Escape:
                CloseEditor();
                e.Handled = true;
                break;
        }
    }

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
        {
            // CS-163：代理对安全截断——emoji 标题不再劈成乱码半字
            var cut = TitleMaxLength;
            if (char.IsHighSurrogate(title[cut - 1]))
                cut--;
            title = title[..cut];
        }
        if (_editingId > 0)
        {
            // CS-164：库层异常（锁/磁盘）不再裸上抛炸窗口——可见反馈
            try { _ = _bookmarks.Rename(_editingId, title); }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"重命名失败：{ex.Message}", "错误",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
        }
        CloseEditor();
        Reload(SearchBox.Text);
        _owner?.RefreshBookmarkBar();
    }

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: BookmarkRow row })
        {
            // CS-164：删除失败可见反馈
            try { _ = _bookmarks.RemoveById(row.Id); }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"删除失败：{ex.Message}", "错误",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
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
        // CS-164：清空失败可见反馈
        try { _bookmarks.ClearAll(); }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"清空失败：{ex.Message}", "错误",
                MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }
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
            // CS-164：键盘删除路径同样捕获反馈
            try { _ = _bookmarks.RemoveById(del.Id); }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"删除失败：{ex.Message}", "错误",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
            Reload(SearchBox.Text);
            _owner?.RefreshBookmarkBar();
            e.Handled = true;
        }
    }

    private long _editingId;

    public sealed record BookmarkRow(long Id, string Title, string Url);
}

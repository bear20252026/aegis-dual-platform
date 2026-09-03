namespace Aegis.Windows.Chrome;

using System.Linq;
using System.Windows;
using Aegis.Windows.Core.History;

/// <summary>历史记录窗口（M2：查看/搜索/清除——Python 栈「只写不清」的
/// 隐私合规缺口在正典栈补齐）。清除为不可恢复操作——二次确认。</summary>
public partial class HistoryWindow : Window
{
    private readonly HistoryStore _history;

    public HistoryWindow(HistoryStore history)
    {
        InitializeComponent();
        _history = history;
        Loaded += (_, _) => Reload("");
    }

    private void Reload(string query)
    {
        var entries = string.IsNullOrWhiteSpace(query)
            ? _history.Recent(200)
            : _history.Search(query, 200);
        HistoryList.ItemsSource = entries
            .Select(e => new HistoryRow(e.Title, e.Url, e.VisitedAt));
    }

    private void SearchBox_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e) =>
        Reload(SearchBox.Text);

    private void Clear_Click(object sender, RoutedEventArgs e)
    {
        var confirmed = MessageBox.Show(
            this,
            "将清除全部历史记录，且不可恢复。确定继续？",
            "清除历史",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (confirmed != MessageBoxResult.Yes)
            return;
        _history.Clear();
        Reload("");
        MessageBox.Show(this, "历史记录已清空。", "完成", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    /// <summary>列表行视图（title/url/本地时间——无 token 泄露面：仅本地展示）。</summary>
    public sealed record HistoryRow(string Title, string Url, string VisitedAt);
}

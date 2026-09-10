namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Threading;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.History;

/// <summary>地址栏建议行（书签/历史来源标注）。</summary>
public sealed record SuggestionRow(string Url, string Title, string Kind);

/// <summary>地址栏自动补全控制器（MainWindow 上帝对象拆分·第一批）：防抖、
/// 书签/历史后台查询（书签全表 + SQLite LIKE 移出 UI 线程）、乱序防护与
/// 弹层管理。合并/去重为纯静态——可脱离数据源单测。</summary>
public sealed class SuggestionController
{
    public const int MaxRows = 8;
    public const int HistoryScanRows = 60;
    public const int DebounceMs = 150;

    private readonly TextBox _addressBar;
    private readonly Popup _popup;
    private readonly ListBox _list;
    private readonly BookmarkStore _bookmarks;
    private readonly HistoryStore _history;
    private readonly Action _navigate;
    private readonly DispatcherTimer _timer;
    private string? _lastQuery;

    public SuggestionController(
        TextBox addressBar,
        Popup popup,
        ListBox list,
        BookmarkStore bookmarks,
        HistoryStore history,
        Action navigate)
    {
        _addressBar = addressBar ?? throw new ArgumentNullException(nameof(addressBar));
        _popup = popup ?? throw new ArgumentNullException(nameof(popup));
        _list = list ?? throw new ArgumentNullException(nameof(list));
        _bookmarks = bookmarks ?? throw new ArgumentNullException(nameof(bookmarks));
        _history = history ?? throw new ArgumentNullException(nameof(history));
        _navigate = navigate ?? throw new ArgumentNullException(nameof(navigate));
        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(DebounceMs) };
        _timer.Tick += (_, _) => Run();
    }

    /// <summary>地址栏文本变化——重启防抖计时（逐键不即时查询）。</summary>
    public void OnTextChanged()
    {
        _timer.Stop();
        _timer.Start();
    }

    /// <summary>停掉待发的防抖查询（窗口关闭/导航提交时）。</summary>
    public void StopDebounce() => _timer.Stop();

    /// <summary>立即执行建议查询（防抖到期）：空输入关弹层；否则后台构建，
    /// 回到 UI 线程前校验输入未变（迟到的旧结果不覆盖新输入）。</summary>
    public void Run()
    {
        _timer.Stop();
        var query = _addressBar.Text.Trim();
        if (query.Length == 0)
        {
            _popup.IsOpen = false;
            return;
        }
        var captured = query;
        _ = Task.Run(() =>
        {
            var rows = BuildSuggestions(captured);
            _addressBar.Dispatcher.BeginInvoke(() =>
            {
                if (!string.Equals(_addressBar.Text.Trim(), captured, StringComparison.Ordinal))
                    return;
                _lastQuery = captured;
                _list.ItemsSource = rows;
                _popup.IsOpen = rows.Count > 0;
            });
        });
    }

    /// <summary>最近一次生效查询（诊断/测试用）。</summary>
    public string? LastQuery => _lastQuery;

    private List<SuggestionRow> BuildSuggestions(string query)
    {
        var hits = _history.Search(query.ToLowerInvariant(), null, HistoryScanRows);
        return MergeRows(query, _bookmarks.All(), hits, MaxRows);
    }

    /// <summary>纯合并（可单测）：书签全表 + 历史命中 → 不区分大小写包含匹配、
    /// URL 去重（书签优先）、上限截断。空标题回退显示 URL。</summary>
    public static List<SuggestionRow> MergeRows(
        string query,
        IEnumerable<Bookmark> bookmarks,
        IEnumerable<HistoryEntry> historyHits,
        int maxRows)
    {
        var q = query.ToLowerInvariant();
        var rows = new List<SuggestionRow>();
        var seenUrls = new HashSet<string>(StringComparer.Ordinal);
        foreach (var b in bookmarks)
            if ((b.Title.ToLowerInvariant().Contains(q) || b.Url.ToLowerInvariant().Contains(q))
                && seenUrls.Add(b.Url))
                rows.Add(new SuggestionRow(b.Url, string.IsNullOrWhiteSpace(b.Title) ? b.Url : b.Title, "书签"));
        foreach (var h in historyHits)
        {
            if (h.Url.ToLowerInvariant().Contains(q) && seenUrls.Add(h.Url))
            {
                rows.Add(new SuggestionRow(h.Url, string.IsNullOrWhiteSpace(h.Title) ? h.Url : h.Title, "历史"));
                if (rows.Count >= maxRows) break;
            }
        }
        return rows.Take(maxRows).ToList();
    }

    /// <summary>选中建议项：关弹层、地址栏回填 URL 并导航。</summary>
    public void Pick(SuggestionRow row)
    {
        _popup.IsOpen = false;
        _addressBar.Text = row.Url;
        _addressBar.CaretIndex = row.Url.Length;
        _navigate();
    }

    /// <summary>弹层展开且有可选行（地址栏键盘循环导航的前提）。</summary>
    public bool IsOpenWithItems => _popup.IsOpen && _list.Items.Count > 0;

    /// <summary>上下键循环移动选中项（返回是否处理了该键）。</summary>
    public bool MoveSelection(int delta)
    {
        if (_list.Items.Count == 0)
            return false;
        _list.SelectedIndex = ((_list.SelectedIndex + delta) % _list.Items.Count + _list.Items.Count) % _list.Items.Count;
        return true;
    }

    /// <summary>取当前选中项（无选中返回 null）。</summary>
    public SuggestionRow? Selected() => _list.SelectedItem as SuggestionRow;

    /// <summary>关闭弹层（Escape/失焦/提交后）。</summary>
    public void Close() => _popup.IsOpen = false;
}

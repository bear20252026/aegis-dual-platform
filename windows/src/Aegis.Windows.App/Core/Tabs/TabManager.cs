namespace Aegis.Windows.Core.Tabs;

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;

/// <summary>标签集合管理器（ADR-009 D2 领域层——纯逻辑，无 UI/WebView 依赖）。
/// 职责：标签集合与当前标签状态机、固定（Pinned 前置分区）、关闭撤销栈
/// （重新打开已关闭标签）、批量关闭（关闭其他/右侧）。
/// 事件回调在 UI 线程由调用方保证。</summary>
public sealed class TabManager
{
    private readonly ObservableCollection<Tab> _tabs = new();
    private int _currentIndex;
    private readonly Stack<Tab> _closed = new();

    /// <summary>新标签打开（UI 创建 WebView 实例并挂接）。</summary>
    public event Action<Tab>? TabOpened;

    /// <summary>标签关闭（UI 摘除并 dispose 对应 WebView 实例；参数=被关闭 tabId）。
    /// 显式访问器——规避 CS0067 字段式事件误报（本事件确实被主/无痕窗口订阅）。</summary>
    private Action<string>? _tabClosed;
    public event Action<string>? TabClosed
    {
        add => _tabClosed += value;
        remove => _tabClosed -= value;
    }

    /// <summary>当前标签切换（UI 切换可见性并同步地址栏）。</summary>
    public event Action<Tab>? TabSwitched;

    /// <summary>只读标签视图（Observable——原生标签条直接绑定，增删自动刷新）。</summary>
    public ReadOnlyObservableCollection<Tab> Tabs { get; }

    public TabManager() => Tabs = new ReadOnlyObservableCollection<Tab>(_tabs);

    /// <summary>当前标签（可能为 null——全部关闭的瞬态）。</summary>
    public Tab? Current => _currentIndex >= 0 && _currentIndex < _tabs.Count ? _tabs[_currentIndex] : null;

    /// <summary>当前标签的 TabId（无当前标签返回 null）。</summary>
    public string? CurrentTabId => Current?.TabId;

    /// <summary>已关闭标签快照数（撤销可用性）。</summary>
    public int ClosedCount => _closed.Count;

    /// <summary>固定标签数量（前置分区边界）。</summary>
    public int PinnedCount => _tabs.Count(t => t.IsPinned);

    /// <summary>新建标签并激活。url 为该标签初始加载地址（导航仍经 broker 决策）。</summary>
    public Tab NewTab(string url, string title = "新标签页")
    {
        var tab = new Tab(Guid.NewGuid().ToString("N"), url, title);
        var insertAt = _tabs.Count;  // 新标签追加到末尾（固定区始终在前）
        _tabs.Insert(insertAt, tab);
        _currentIndex = _tabs.IndexOf(tab);
        TabOpened?.Invoke(tab);
        TabSwitched?.Invoke(tab);
        return tab;
    }

    /// <summary>复制标签（同 URL 新标签并激活）。</summary>
    public Tab? Duplicate(string tabId)
    {
        var source = _tabs.FirstOrDefault(t => t.TabId == tabId);
        return source is null ? null : NewTab(source.Url, source.Title);
    }

    /// <summary>固定/取消固定。固定 → 移入前置分区末尾；取消 → 移到非固定区首位。
    /// 激活标签保持不变（仅位置移动）。</summary>
    public void SetPinned(string tabId, bool pinned)
    {
        var tab = _tabs.FirstOrDefault(t => t.TabId == tabId);
        if (tab is null || tab.IsPinned == pinned)
            return;
        var currentId = CurrentTabId;
        tab.IsPinned = pinned;
        var from = _tabs.IndexOf(tab);
        var target = pinned ? PinnedCount - 1 : PinnedCount;
        if (target != from)
            _tabs.Move(from, target);
        _currentIndex = currentId is null
            ? -1
            : _tabs.IndexOf(_tabs.First(t => t.TabId == currentId));
    }

    /// <summary>切换当前标签；未知 tabId 或已是当前为 no-op。</summary>
    public void SwitchTo(string tabId)
    {
        var target = _tabs.FirstOrDefault(t => t.TabId == tabId);
        if (target is null)
            return;
        var index = _tabs.IndexOf(target);
        if (index < 0 || index == _currentIndex)
            return;
        _currentIndex = index;
        target.LastActivated = DateTime.Now;
        TabSwitched?.Invoke(target);
    }

    /// <summary>关闭标签；若关闭的是当前标签则自动激活相邻后继（优先左侧）。
    /// 关闭的标签入撤销栈（最多 20）。</summary>
    public string? CloseTab(string tabId)
    {
        var target = _tabs.FirstOrDefault(t => t.TabId == tabId);
        if (target is null)
            return CurrentTabId;
        var index = _tabs.IndexOf(target);
        if (index < 0)
            return CurrentTabId;
        var wasCurrent = index == _currentIndex;
        _tabs.RemoveAt(index);
        _closed.Push(target);
        while (_closed.Count > 20)
            _closed.Pop();
        if (_tabs.Count == 0)
        {
            _currentIndex = -1;
            return null;
        }
        if (wasCurrent)
        {
            _currentIndex = Math.Min(index, _tabs.Count - 1);
            TabSwitched?.Invoke(Current!);
        }
        else if (index < _currentIndex)
        {
            _currentIndex--;
        }
        return CurrentTabId;
    }

    /// <summary>拖拽排序（ObservableCollection.Move 保持绑定刷新）。固定分区约束：
    /// 固定标签只能在固定区内部移动、非固定不能移入固定区。当前标签索引随动。</summary>
    public void MoveTab(int fromIndex, int toIndex)
    {
        if (fromIndex < 0 || fromIndex >= _tabs.Count
            || toIndex < 0 || toIndex >= _tabs.Count
            || fromIndex == toIndex)
            return;
        var moving = _tabs[fromIndex];
        var pinned = PinnedCount;
        if (moving.IsPinned && toIndex >= pinned)
            toIndex = pinned - 1;
        else if (!moving.IsPinned && toIndex < pinned)
            toIndex = pinned;
        if (toIndex < 0 || toIndex >= _tabs.Count || toIndex == fromIndex)
            return;
        _tabs.Move(fromIndex, toIndex);
        if (_currentIndex == fromIndex)
            _currentIndex = toIndex;
        else if (fromIndex < _currentIndex && toIndex >= _currentIndex)
            _currentIndex--;
        else if (fromIndex > _currentIndex && toIndex <= _currentIndex)
            _currentIndex++;
    }

    /// <summary>关闭除 keepTabId 外的全部非固定标签。返回是否有关闭。</summary>
    public bool CloseOthers(string keepTabId)
    {
        var closed = false;
        foreach (var id in _tabs.Where(t => !t.IsPinned && t.TabId != keepTabId)
                     .Select(t => t.TabId).ToList())
        {
            CloseTab(id);
            closed = true;
        }
        return closed;
    }

    /// <summary>关闭 tabId 右侧的全部非固定标签。返回是否有关闭。</summary>
    public bool CloseRight(string tabId)
    {
        var tab = _tabs.FirstOrDefault(t => t.TabId == tabId);
        if (tab is null)
            return false;
        var closed = false;
        foreach (var id in _tabs.Skip(_tabs.IndexOf(tab) + 1)
                     .Where(t => !t.IsPinned).Select(t => t.TabId).ToList())
        {
            CloseTab(id);
            closed = true;
        }
        return closed;
    }

    /// <summary>弹出最近关闭的标签快照（null=栈空）。恢复用 NewTab(url,title)。</summary>
    public Tab? PopClosed() => _closed.Count > 0 ? _closed.Pop() : null;

    /// <summary>更新标签标题（页面 DocumentTitle 回填——原生绑定刷新标签条）。</summary>
    public void UpdateTitle(string tabId, string title)
    {
        var tab = _tabs.FirstOrDefault(t => t.TabId == tabId);
        if (tab is not null && !string.IsNullOrWhiteSpace(title))
            tab.Title = title;
    }

    /// <summary>更新标签 URL（页面实际地址回填——地址栏同步数据源）。</summary>
    public void UpdateUrl(string tabId, string url)
    {
        var tab = _tabs.FirstOrDefault(t => t.TabId == tabId);
        if (tab is not null && !string.IsNullOrWhiteSpace(url))
            tab.Url = url;
    }

    /// <summary>会话恢复：清空后按给定顺序重建标签集合（不触发 TabOpened/TabSwitched——
    /// UI 层在恢复流程中自行批量创建 WebView；本方法只负责领域状态）。
    /// 返回当前激活的 TabId。</summary>
    /// <summary>会话恢复：先物化输入（避免重复消费 IEnumerable/依赖 ICollection 推断），
    /// 清空重建标签集合（不触发 TabOpened/TabSwitched——UI 层批量创建 WebView）。
    /// currentTabId 缺失时稳定回退到末位标签。</summary>
    public string? SeedSession(IEnumerable<(string TabId, string Url, string Title, bool IsPinned)> tabs, string? currentTabId)
    {
        var materialized = tabs.ToList();
        _tabs.Clear();
        _closed.Clear();
        foreach (var (tabId, url, title, isPinned) in materialized)
        {
            var tab = new Tab(tabId, url, title) { IsPinned = isPinned };
            _tabs.Add(tab);
        }
        _currentIndex = materialized.Count - 1;
        var hit = materialized.FindIndex(t => t.TabId == currentTabId);
        if (hit >= 0)
            _currentIndex = hit;
        return CurrentTabId;
    }
}

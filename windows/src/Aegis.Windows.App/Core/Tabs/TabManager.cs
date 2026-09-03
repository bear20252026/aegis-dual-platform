namespace Aegis.Windows.Core.Tabs;

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;

/// <summary>标签集合管理器（ADR-009 D2 领域层——纯逻辑，无 UI/WebView 依赖，
/// 全量可单测）。负责标签集合与当前标签的状态机；UI 层经事件挂接每标签的
/// WebView 实例生命周期（创建/激活/销毁——安全顺序：先摘视觉树再 dispose）。
/// 事件回调在 UI 线程由调用方保证（Chrome 层接线）。</summary>
public sealed class TabManager
{
    private readonly ObservableCollection<Tab> _tabs = new();
    private int _currentIndex;

    /// <summary>新标签打开（UI 创建 WebView 实例并挂接）。</summary>
    public event Action<Tab>? TabOpened;

    /// <summary>标签关闭（UI 摘除并 dispose 对应 WebView 实例；参数=被关闭 tabId）。</summary>
    public event Action<string>? TabClosed;

    /// <summary>当前标签切换（UI 切换可见性并同步地址栏）。</summary>
    public event Action<Tab>? TabSwitched;

    /// <summary>只读标签视图（Observable——原生标签条直接绑定，增删自动刷新）。</summary>
    public ReadOnlyObservableCollection<Tab> Tabs { get; }

    public TabManager() => Tabs = new ReadOnlyObservableCollection<Tab>(_tabs);

    /// <summary>当前标签（可能为 null——全部关闭的瞬态）。</summary>
    public Tab? Current => _currentIndex >= 0 && _currentIndex < _tabs.Count ? _tabs[_currentIndex] : null;

    /// <summary>当前标签的 TabId（无当前标签返回 null）。</summary>
    public string? CurrentTabId => Current?.TabId;

    /// <summary>新建标签并激活。url 为该标签初始加载地址（导航仍经 broker 决策）。</summary>
    public Tab NewTab(string url, string title = "新标签页")
    {
        var tab = new Tab(Guid.NewGuid().ToString("N"), url, title);
        _tabs.Add(tab);
        _currentIndex = _tabs.Count - 1;
        TabOpened?.Invoke(tab);
        TabSwitched?.Invoke(tab);
        return tab;
    }

    /// <summary>关闭标签；若关闭的是当前标签则自动激活相邻后继（优先左侧）。
    /// 返回关闭后的当前 TabId（全部关闭返回 null）。未知 tabId 为 no-op。</summary>
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
        TabClosed?.Invoke(tabId);
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
        TabSwitched?.Invoke(Current!);
    }

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
    public string? SeedSession(IEnumerable<(string TabId, string Url, string Title)> tabs, string? currentTabId)
    {
        _tabs.Clear();
        foreach (var (tabId, url, title) in tabs)
            _tabs.Add(new Tab(tabId, url, title));
        _currentIndex = tabs is ICollection<(string, string, string)> c ? c.Count - 1 : -1;
        var current = _tabs.FirstOrDefault(t => t.TabId == currentTabId) ?? Current;
        if (current is not null)
            _currentIndex = _tabs.IndexOf(current);
        return CurrentTabId;
    }
}

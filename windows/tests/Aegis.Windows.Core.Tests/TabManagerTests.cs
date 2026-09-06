namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>M1-T1（ADR-009）：TabManager 领域状态机单测——纯逻辑无 UI 依赖
/// （领域层可单测是 ADR-009 D2 的架构要求）。</summary>
public sealed class TabManagerTests
{
    [Fact]
    public void NewTabAddsAndSwitchesToIt()
    {
        var manager = new TabManager();
        var opened = new List<Tab>();
        var switched = new List<Tab>();
        manager.TabOpened += t => opened.Add(t);
        manager.TabSwitched += t => switched.Add(t);

        var first = manager.NewTab("about:blank");
        var second = manager.NewTab("https://example.com");

        Assert.Equal(2, manager.Tabs.Count);
        Assert.Equal(2, opened.Count);
        Assert.Equal(second.TabId, manager.CurrentTabId);
        Assert.Equal([first, second], switched);
    }

    [Fact]
    public void ClosingCurrentTabActivatesNeighborPreferentially()
    {
        var manager = new TabManager();
        var t1 = manager.NewTab("about:blank");
        _ = manager.NewTab("about:blank");
        var t3 = manager.NewTab("about:blank");

        manager.SwitchTo(t3.TabId);
        var current = manager.CloseTab(t3.TabId);

        Assert.Equal(t1.TabId, manager.Tabs[0].TabId);
        // 关闭末位 → 后继是左侧邻居
        Assert.Equal(manager.Tabs[^1].TabId, current);
    }

    [Fact]
    public void ClosingLeftTabKeepsCurrentIndexStable()
    {
        var manager = new TabManager();
        _ = manager.NewTab("about:blank");
        var second = manager.NewTab("about:blank");
        _ = manager.NewTab("about:blank");
        manager.SwitchTo(second.TabId);

        manager.CloseTab(manager.Tabs[0].TabId);

        // 关闭的是左侧标签——当前标签不变（同一 tabId）
        Assert.Equal(second.TabId, manager.CurrentTabId);
    }

    [Fact]
    public void ClosingLastTabReturnsNull()
    {
        var manager = new TabManager();
        _ = manager.NewTab("about:blank");

        Assert.Null(manager.CloseTab(manager.Tabs[0].TabId));
        Assert.Null(manager.Current);
        Assert.Empty(manager.Tabs);
    }

    [Fact]
    public void CloseUnknownTabIsNoOp()
    {
        var manager = new TabManager();
        _ = manager.NewTab("about:blank");

        Assert.Equal(manager.CurrentTabId, manager.CloseTab("nonexistent"));
        Assert.Single(manager.Tabs);
    }

    [Fact]
    public void UpdateTitleAndUrlOnlyAffectTargetTab()
    {
        var manager = new TabManager();
        var first = manager.NewTab("https://a.example");
        _ = manager.NewTab("https://b.example");

        manager.UpdateTitle(first.TabId, "示例页");
        manager.UpdateUrl(first.TabId, "https://a.example/page");

        Assert.Equal("示例页", manager.Tabs[0].Title);
        Assert.Equal("https://a.example/page", manager.Tabs[0].Url);
        Assert.Equal("https://b.example", manager.Tabs[1].Url);
    }

    [Fact]
    public void TitleChangeRaisesPropertyChanged()
    {
        // 原生标签条绑定依赖 INotifyPropertyChanged（架构性修复「标签标题
        // 永不更新」——此处锁死通知契约）
        var manager = new TabManager();
        var tab = manager.NewTab("about:blank");
        var notified = new List<string?>();
        tab.PropertyChanged += (_, e) => notified.Add(e.PropertyName);

        tab.Title = "新标题";

        Assert.Contains(nameof(Tab.Title), notified);
    }

    [Fact]
    public void SeedSessionRebuildsAndRespectsCurrent()
    {
        var manager = new TabManager();
        _ = manager.NewTab("about:blank");

        var restored = manager.SeedSession(
        [
            ("tab-a", "https://a.example", "A", false),
            ("tab-b", "https://b.example", "B", false),
        ], "tab-b");

        Assert.Equal(2, manager.Tabs.Count);
        Assert.Equal("tab-b", restored);
        Assert.Equal("https://b.example", manager.Current?.Url);
    }

    [Fact]
    public void SeedSessionWithUnknownCurrentFallsBackToLast()
    {
        var manager = new TabManager();

        var restored = manager.SeedSession(
        [
            ("tab-a", "https://a.example", "A", false),
            ("tab-b", "https://b.example", "B", false),
        ], "missing");

        Assert.Equal("tab-b", restored);
    }

    [Fact]
    public void MoveTabReordersAndKeepsCurrentActive()
    {
        var manager = new TabManager();
        var t1 = manager.NewTab("about:blank");
        var t2 = manager.NewTab("about:blank");
        var t3 = manager.NewTab("about:blank");

        manager.MoveTab(0, 2);

        Assert.Equal([t2.TabId, t3.TabId, t1.TabId], manager.Tabs.Select(t => t.TabId));
        Assert.Equal(t3.TabId, manager.CurrentTabId);
    }

    [Fact]
    public void MoveTabAcrossCurrentAdjustsCurrentIndex()
    {
        var manager = new TabManager();
        var t1 = manager.NewTab("about:blank");
        var t2 = manager.NewTab("about:blank");
        var t3 = manager.NewTab("about:blank");
        manager.SwitchTo(t3.TabId);

        manager.MoveTab(2, 0);

        Assert.Equal(t3.TabId, manager.CurrentTabId);
        Assert.Equal([t3.TabId, t1.TabId, t2.TabId], manager.Tabs.Select(t => t.TabId));
    }

    [Fact]
    public void PinnedTabMovesToFrontAndUnpinRestores()
    {
        var m = new TabManager();
        var a = m.NewTab("https://a"); _ = m.NewTab("https://b"); var c = m.NewTab("https://c");
        m.SetPinned(a.TabId, true);
        Assert.True(m.Tabs[0].IsPinned);
        m.SetPinned(a.TabId, false);
        Assert.False(m.Tabs[0].IsPinned);
        Assert.Equal(3, m.Tabs.Count);
        Assert.Equal(c.TabId, m.CurrentTabId);  // 激活标签不变
    }

    [Fact]
    public void NewTabInsertedAfterPinnedBlock()
    {
        var m = new TabManager();
        var a = m.NewTab("https://a");
        m.SetPinned(a.TabId, true);
        var b = m.NewTab("https://b");
        Assert.Equal(a.TabId, m.Tabs[0].TabId);  // 固定区首位
        Assert.Equal(b.TabId, m.Tabs[1].TabId);  // 新标签排固定区后
        Assert.True(m.Current!.TabId == b.TabId);
    }

    [Fact]
    public void ClosedTabGoesToUndoStack()
    {
        var m = new TabManager();
        var a = m.NewTab("https://a"); var b = m.NewTab("https://b");
        m.CloseTab(a.TabId);
        Assert.Equal(1, m.ClosedCount);
        var popped = m.PopClosed();
        Assert.NotNull(popped);
        Assert.Equal("https://a", popped!.Url);
        Assert.Equal(0, m.ClosedCount);
    }

    [Fact]
    public void CloseOthersKeepsPinnedAndTarget()
    {
        var m = new TabManager();
        var a = m.NewTab("https://a"); var b = m.NewTab("https://b"); var c = m.NewTab("https://c");
        m.SetPinned(a.TabId, true);
        var closed = m.CloseOthers(b.TabId);
        Assert.True(closed);
        Assert.Equal(2, m.Tabs.Count);
        Assert.Contains(m.Tabs, x => x.TabId == a.TabId);
        Assert.Contains(m.Tabs, x => x.TabId == b.TabId);
        Assert.DoesNotContain(m.Tabs, x => x.TabId == c.TabId);
    }

    [Fact]
    public void CloseRightClosesFollowingNonPinned()
    {
        var m = new TabManager();
        _ = m.NewTab("https://a"); var b = m.NewTab("https://b"); _ = m.NewTab("https://c"); _ = m.NewTab("https://d");
        m.CloseRight(b.TabId);
        Assert.Equal(["https://a", "https://b"], m.Tabs.Select(x => x.Url).ToList());
    }

    [Fact]
    public void MoveTabInvalidArgumentsAreNoOp()
    {
        var manager = new TabManager();
        var t1 = manager.NewTab("about:blank");
        var t2 = manager.NewTab("about:blank");

        manager.MoveTab(-1, 1);
        manager.MoveTab(0, 5);
        manager.MoveTab(1, 1);

        Assert.Equal(t1.TabId, manager.Tabs[0].TabId);
        Assert.Equal(t2.TabId, manager.CurrentTabId);
    }


    [Fact]
    public void SeedSessionFallsBackToLastWhenInsertingPinnedAndNoCurrent()
    {
        // 修复：SeedSession 物化输入，currentTabId 缺失时稳定回退到末位
        var m = new TabManager();
        var restored = m.SeedSession(
            new[] { ("a", "https://a", "A", true), ("b", "https://b", "B", false) },
            currentTabId: null);
        Assert.Equal(2, m.Tabs.Count);
        Assert.Equal("https://b", m.Current?.Url);  // 回退末位
        Assert.Equal("b", restored);
        Assert.True(m.Tabs[0].IsPinned);
    }

    [Fact]
    public void SeedSessionUnknownCurrentFallsBackToLastAgain()
    {
        var m = new TabManager();
        var restored = m.SeedSession(
            new[] { ("x", "https://x", "X", false), ("y", "https://y", "Y", false) },
            currentTabId: "missing");
        Assert.Equal("y", restored);
        Assert.Equal("https://y", m.Current?.Url);
    }

}

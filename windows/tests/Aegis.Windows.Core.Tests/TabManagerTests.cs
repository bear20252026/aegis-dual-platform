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


    [Fact]
    public void CloseTabInvokesTabClosedForSubscriberTeardown()
    {
        // CS-001 回归：TabClosed 此前从未触发——订阅方（主/无痕窗口）的
        // WebView 摘除与 dispose 永不执行，每关一标签泄漏一个 WebView2 实例
        var manager = new TabManager();
        var t1 = manager.NewTab("about:blank");
        var t2 = manager.NewTab("about:blank");
        var closedIds = new List<string>();
        manager.TabClosed += id => closedIds.Add(id);

        manager.CloseTab(t1.TabId);
        Assert.Equal([t1.TabId], closedIds);

        manager.CloseTab(t2.TabId);
        Assert.Equal([t1.TabId, t2.TabId], closedIds);
    }

    [Fact]
    public void CloseOthersAndCloseRightInvokeTabClosedForEach()
    {
        var manager = new TabManager();
        var t1 = manager.NewTab("about:blank");
        var t2 = manager.NewTab("about:blank");
        var t3 = manager.NewTab("about:blank");
        var closedIds = new List<string>();
        manager.TabClosed += id => closedIds.Add(id);

        manager.CloseRight(t1.TabId);
        Assert.Equal([t2.TabId, t3.TabId], closedIds);

        closedIds.Clear();
        var t4 = manager.NewTab("about:blank");
        manager.CloseOthers(t4.TabId);
        Assert.Equal([t1.TabId], closedIds);
    }

    // ===== C19a 批（审计 2026-09-26）：CS-264..271 补测 =====

    [Fact]
    public void Duplicate_CreatesNewTabWithSameUrlAndActivates()
    {
        // CS-264：复制标签——新 id/同 URL/激活新标签
        var manager = new TabManager();
        var source = manager.NewTab("https://example.com", "示例");

        var copy = manager.Duplicate(source.TabId);

        Assert.NotNull(copy);
        Assert.NotEqual(source.TabId, copy!.TabId);
        Assert.Equal("https://example.com", copy.Url);
        Assert.Equal("示例", copy.Title);
        Assert.Equal(copy.TabId, manager.CurrentTabId);
    }

    [Fact]
    public void Duplicate_UnknownIdReturnsNull()
    {
        Assert.Null(new TabManager().Duplicate("no-such-tab"));
    }

    [Fact]
    public void PopClosed_EmptyStackReturnsNull_AndLifoOrder()
    {
        // CS-265：空栈 null；多入栈后 LIFO 弹出
        var manager = new TabManager();
        Assert.Null(manager.PopClosed());

        var t1 = manager.NewTab("https://one.example");
        var t2 = manager.NewTab("https://two.example");
        manager.CloseTab(t1.TabId);
        manager.CloseTab(t2.TabId);

        Assert.Equal(t2.TabId, manager.PopClosed()!.TabId);  // 后关先弹
        Assert.Equal(t1.TabId, manager.PopClosed()!.TabId);
        Assert.Null(manager.PopClosed());
    }

    [Fact]
    public void UndoStack_EvictsOldestBeyondCapacity()
    {
        // CS-266：21 次关闭后栈保持 20——最早关闭的标签被淘汰
        var manager = new TabManager();
        var first = manager.NewTab("https://first.example");
        for (var i = 0; i < 20; i++)
        {
            var t = manager.NewTab($"https://x{i}.example");
            manager.CloseTab(t.TabId);
        }
        Assert.Equal(20, manager.ClosedCount);

        manager.CloseTab(first.TabId);
        Assert.Equal(20, manager.ClosedCount);  // 容量恒定
        var seen = new List<string>();
        while (manager.PopClosed() is { } tab)
            seen.Add(tab.TabId);
        Assert.DoesNotContain(first.TabId, seen);
        Assert.Equal(20, seen.Count);
    }

    [Fact]
    public void SetPinned_UnknownIdIsNoOp()
    {
        // CS-267：未知 id 固定请求不影响集合
        var manager = new TabManager();
        manager.NewTab("https://a.example");
        manager.SetPinned("no-such-tab", true);
        Assert.Equal(0, manager.PinnedCount);
    }

    [Fact]
    public void UpdateTitle_BlankOrWhitespaceIgnored()
    {
        // CS-268：空白标题不覆盖既有标题
        var manager = new TabManager();
        var tab = manager.NewTab("https://a.example", "原标题");
        manager.UpdateTitle(tab.TabId, "  ");
        Assert.Equal("原标题", tab.Title);
        manager.UpdateTitle("no-such", "任意");
        Assert.Equal("原标题", tab.Title);
    }

    [Fact]
    public void SeedSession_ClearsUndoStack()
    {
        // CS-269：会话重建清空撤销栈——旧会话关闭历史不可跨会话复活
        var manager = new TabManager();
        var t = manager.NewTab("https://a.example");
        manager.CloseTab(t.TabId);
        Assert.Equal(1, manager.ClosedCount);

        manager.SeedSession([("s1", "https://s.example", "S", false)], "s1");

        Assert.Equal(0, manager.ClosedCount);
        Assert.Null(manager.PopClosed());
    }

    [Fact]
    public void NewTab_FiresOpenedThenSwitched_InOrder()
    {
        // CS-270：NewTab 先 Opened 后 Switched；SwitchTo 已当前 no-op 不触发
        var manager = new TabManager();
        var events = new List<string>();
        manager.TabOpened += t => events.Add("opened");
        manager.TabSwitched += t => events.Add("switched");

        var tab = manager.NewTab("https://a.example");

        Assert.Equal(["opened", "switched"], events);

        events.Clear();
        manager.SwitchTo(tab.TabId);
        Assert.Empty(events);
    }

    [Fact]
    public void CloseTab_EventSequence_ClosedThenSwitched()
    {
        // CS-271：关闭当前标签先 Closed 后 Switched（摘 WebView 先于激活后继）
        var manager = new TabManager();
        var t1 = manager.NewTab("https://a.example");
        var t2 = manager.NewTab("https://b.example");
        manager.SwitchTo(t1.TabId);
        var events = new List<string>();
        manager.TabClosed += id => events.Add($"closed:{id}");
        manager.TabSwitched += t => events.Add($"switched:{t.TabId}");

        manager.CloseTab(t1.TabId);

        Assert.Equal([$"closed:{t1.TabId}", $"switched:{t2.TabId}"], events);
    }
}

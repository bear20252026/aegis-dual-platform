package com.aegis.browser

import android.webkit.WebView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito.inOrder
import org.mockito.Mockito.mock
import org.mockito.Mockito.times

/**
 * TabManager 离线单测（测试缺口批次·Android）：LRU 挂起上限、切换挂起/恢复
 * 、关闭边界约定（至少保留一个）、标题替换实例语义（StateFlow 发射依赖）、
 * 渲染进程崩溃原位替换、suspendAll 空列表安全。
 *
 * WebView 为 mockable 桩（returnDefaultValues）；pause/resume 注入记录调用。
 */
class TabManagerTest {
    private class Recorder {
        val paused = mutableListOf<WebView>()
        val resumed = mutableListOf<WebView>()

        val pause: (WebView) -> Unit = { paused.add(it) }
        val resume: (WebView) -> Unit = { resumed.add(it) }
    }

    private fun newWebView(): WebView = WebView(android.app.Application())

    private fun manager(
        rec: Recorder,
        maxActive: Int = 8,
    ) = TabManager(maxActive = maxActive, pause = rec.pause, resume = rec.resume)

    @Test
    fun addTab_activatesNewTab_andSequencesIds() {
        val rec = Recorder()
        val tm = manager(rec)
        val first = tm.addTab(newWebView(), url = "https://a.example")
        val second = tm.addTab(newWebView(), url = "https://b.example")
        assertEquals(0L, first.id)
        assertEquals(1L, second.id)
        assertEquals(2, tm.size)
        assertSame(second, tm.current())
        assertEquals(1, tm.activeIndex)
    }

    @Test
    fun switchTo_outOfBounds_returnsFalse() {
        val rec = Recorder()
        val tm = manager(rec)
        tm.addTab(newWebView())
        assertFalse(tm.switchTo(-1))
        assertFalse(tm.switchTo(5))
        assertTrue(tm.switchTo(0))
    }

    @Test
    fun switchTo_pausesPrevious_andResumesSuspendedTarget() {
        val rec = Recorder()
        val tm = manager(rec, maxActive = 1)
        tm.addTab(newWebView()) // tab0 激活
        tm.addTab(newWebView()) // tab1 激活——超过上限 1，tab0（最久未用）被挂起
        assertEquals(listOf(0L), tm.list().filter { it.suspended }.map { it.id })
        assertTrue(tm.switchTo(0)) // 切回挂起标签 → 恢复
        assertFalse(tm.list().first { it.id == 0L }.suspended)
        assertTrue(rec.resumed.isNotEmpty())
        // 原激活标签（tab1）被挂起
        assertTrue(tm.list().first { it.id == 1L }.suspended)
    }

    @Test
    fun closeTab_keepsAtLeastOne_andActivatesNeighbor() {
        val rec = Recorder()
        val tm = manager(rec)
        tm.addTab(newWebView())
        tm.addTab(newWebView())
        assertTrue(tm.closeTab(1)) // 2 个时可关
        assertEquals(1, tm.size)
        // 关闭唯一剩余标签被拒绝（浏览器约定：至少保留一个）
        assertFalse(tm.closeTab(0))
        assertEquals(1, tm.size)
    }

    @Test
    fun closeTab_outOfBounds_returnsFalse() {
        val rec = Recorder()
        val tm = manager(rec)
        tm.addTab(newWebView())
        assertFalse(tm.closeTab(-1))
        assertFalse(tm.closeTab(9))
    }

    @Test
    fun closeTab_lastTab_activatesPredecessor() {
        val rec = Recorder()
        val tm = manager(rec)
        tm.addTab(newWebView()) // 0
        tm.addTab(newWebView()) // 1
        tm.addTab(newWebView()) // 2 激活
        assertTrue(tm.closeTab(2)) // 关闭末位 → 激活前一个
        assertEquals(1, tm.activeIndex)
        assertNotNull(tm.current())
        assertTrue(tm.closeTab(0)) // 关闭头部 → 激活原索引处（后移一位）
        assertEquals(0, tm.activeIndex)
    }

    @Test
    fun replaceWebView_returnsOld_andKeepsIdentityFields() {
        val rec = Recorder()
        val tm = manager(rec)
        val original = newWebView()
        val tab = tm.addTab(original, url = "https://a.example")
        val replacement = newWebView()
        val old = tm.replaceWebView(0, replacement)
        assertSame(original, old)
        val updated = tm.list().first { it.id == tab.id }
        assertSame(replacement, updated.webView)
        assertEquals("新标签页", updated.title)
        assertNull(tm.replaceWebView(9, newWebView()))
    }

    @Test
    fun updateTitle_replacesInstance_soStateFlowNotices() {
        val rec = Recorder()
        val tm = manager(rec)
        val tab = tm.addTab(newWebView())
        val before = tm.list().first { it.id == tab.id }
        tm.updateTitle(tab.id, "新标题")
        val after = tm.list().first { it.id == tab.id }
        // 实例替换（而非原地改 var）——StateFlow 依赖 equals 感知变化
        assertFalse(before === after)
        assertEquals("新标题", after.title)
        assertEquals("新标签页", before.title) // 旧快照不受影响
        // 未知 id 静默忽略
        tm.updateTitle(999L, "x")
    }

    /** AD-036（2026-09-24 审计）：updateUrl 与 updateTitle 同模式——copy 替换实例。 */
    @Test
    fun updateUrl_replacesInstance_soStateFlowNotices() {
        val rec = Recorder()
        val tm = manager(rec)
        val tab = tm.addTab(newWebView(), url = "https://a.example")
        val before = tm.list().first { it.id == tab.id }
        tm.updateUrl(tab.id, "https://b.example")
        val after = tm.list().first { it.id == tab.id }
        assertFalse(before === after)
        assertEquals("https://b.example", after.url)
        assertEquals("https://a.example", before.url) // 旧快照不受影响
        // 未知 id 静默忽略
        tm.updateUrl(999L, "https://ignored.example")
    }

    /** AD-060（2026-09-24 审计）：replaceWebView 重置 suspended——新 WebView 是运行态。 */
    @Test
    fun replaceWebView_resetsStaleSuspendedFlag() {
        val rec = Recorder()
        val tm = manager(rec, maxActive = 1)
        tm.addTab(newWebView()) // tab0
        tm.addTab(newWebView()) // tab1 激活——tab0 被 LRU 挂起
        assertTrue(tm.list().first { it.id == 0L }.suspended)
        tm.replaceWebView(0, newWebView())
        // 替换进来的 WebView 从未 pause——沿用 suspended=true 属状态失真
        assertFalse(tm.list().first { it.id == 0L }.suspended)
    }

    /** AD-056（2026-09-24 审计）：addTab 超上限即时挂起最旧标签（无需切换操作）。 */
    @Test
    fun addTabBeyondLimit_suspendsImmediatelyOnAdd() {
        val rec = Recorder()
        val tm = manager(rec, maxActive = 2)
        tm.addTab(newWebView()) // 0
        tm.addTab(newWebView()) // 1
        val pausesBefore = rec.paused.size
        tm.addTab(newWebView()) // 2——超出上限，tab0（最久未用）立即挂起
        assertEquals(pausesBefore + 1, rec.paused.size)
        assertTrue(tm.list().first { it.id == 0L }.suspended)
    }

    @Test
    fun suspendAll_marksAllSuspended_andSafeOnEmpty() {
        val rec = Recorder()
        val tm = manager(rec)
        tm.suspendAll() // 空列表不抛（P2 修复回归）
        tm.addTab(newWebView())
        tm.addTab(newWebView())
        tm.suspendAll()
        assertTrue(tm.list().all { it.suspended })
        tm.suspendAll() // 幂等：已挂起不重复 pause
        assertEquals(2, rec.paused.count())
    }

    @Test
    fun maxActive_suspendsLeastRecentlyUsed() {
        val rec = Recorder()
        val tm = manager(rec, maxActive = 2)
        tm.addTab(newWebView()) // 0
        tm.addTab(newWebView()) // 1
        tm.switchTo(0) // 0 最近使用 → 1 被挂起
        tm.addTab(newWebView()) // 2 激活——前激活 tab0 被换下挂起（LRU）
        val suspended =
            tm
                .list()
                .filter { it.suspended }
                .map { it.id }
                .toSet()
        assertEquals(setOf(0L, 1L), suspended)
        assertEquals(2L, tm.current()?.id) // 新增标签激活
    }

    @Test
    fun pauseForBackground_suspendsAll_andResumeOnForeground_restoresOnlyCurrent() {
        val rec = Recorder()
        val tm = manager(rec)
        val first = tm.addTab(newWebView(), url = "https://a.example")
        val second = tm.addTab(newWebView(), url = "https://b.example")

        tm.suspendAll()
        // 全部挂起（含当前标签）。AD-084：Tab 全 val——状态断言一律经 list()
        // 快照按 id 取最新实例（挂起即 copy 替换，先前持有的引用是旧快照）。
        tm.list().forEach { assertTrue(it.suspended) }

        tm.resumeOnForeground()
        val firstAfter = tm.list().first { it.id == first.id }
        val secondAfter = tm.list().first { it.id == second.id }
        // 仅当前标签（second）恢复
        assertTrue(secondAfter.suspended.not())
        assertTrue(firstAfter.suspended)
        // current() 与 list() 快照持同一规范实例（copy 替换后的列表内对象）
        assertSame(secondAfter, tm.current())
    }

    @Test
    fun pauseAndResumeBackground_emptyTabs_noThrow() {
        val rec = Recorder()
        val tm = manager(rec)
        tm.suspendAll()
        tm.resumeOnForeground()
    }

    // ---------------- AD-116（审计 2026-09-23 清单·A6 批）：同索引切换 no-op ----------------

    @Test
    fun switchToSameIndexDoesNotPauseOrResumeAnything() {
        val rec = Recorder()
        val tm = manager(rec, maxActive = 1)
        tm.addTab(newWebView()) // tab0
        tm.addTab(newWebView()) // tab1 激活，tab0 已挂起
        val pausesBefore = rec.paused.size
        val resumesBefore = rec.resumed.size
        assertTrue(tm.switchTo(1))
        assertEquals("同索引切换不得重复 pause 旧标签", pausesBefore, rec.paused.size)
        assertEquals("同索引切换不得重复 resume 当前标签", resumesBefore, rec.resumed.size)
        assertEquals(1, tm.activeIndex)
    }

    // ---------------- AD-117（审计 2026-09-23 清单·A6 批）：closeTab 先 pause 后 destroy ----------------

    @Test
    fun closeTabPausesWebViewBeforeTearDownDestroy() {
        // 默认 pause=WebView::onPause——用 mockito 顺序校验「释放绘制资源
        // （pause）先于统一销毁序列（destroy）」的既定次序
        val wv = mock(WebView::class.java)
        val tm = TabManager()
        tm.addTab(wv)
        tm.addTab(mock(WebView::class.java)) // 至少保留一个标签的约定：需两个才能关闭
        assertTrue(tm.closeTab(0))
        // wv 被切走（addTab 第二标签）与关闭各 pause 一次——全部先于 destroy
        val order = inOrder(wv)
        order.verify(wv, times(2)).onPause()
        order.verify(wv).destroy()
    }

    // ---------------- AD-118（审计 2026-09-23 清单·A6 批）：list() 浅拷贝语义固化 ----------------

    @Test
    fun listReturnsStructuralSnapshotWithSharedInstances() {
        val rec = Recorder()
        val tm = manager(rec)
        val tab = tm.addTab(newWebView(), url = "https://a.example")
        val first = tm.list()
        val second = tm.list()
        assertFalse("两次 list() 必须是新列表实例（结构防篡改）", first === second)
        assertEquals(first, second)
        // 浅拷贝：列表内为规范 Tab 实例（copy 替换后的列表内对象）——
        // StateFlow 的 equals 发射依赖实例共享语义
        assertSame(tab, first[0])
        // 快照结构不随后续管理器变更增长（新增标签不影响既有快照）
        tm.addTab(newWebView(), url = "https://b.example")
        assertEquals(1, first.size)
        assertEquals(2, tm.list().size)
    }

    // ---------------- AD-254/AD-275（2026-10-01 审计）：后台关闭保持激活位 ----------------

    @Test
    fun closeBackgroundTabAfterActiveKeepsActiveIndexAndSameTab() {
        // 分支一（index > activeIndex）：关闭激活标签之后的后台标签——激活位
        // 不得跳到被关位置，原激活标签保持激活（无激活跳变/无双活跃 WebView）
        val rec = Recorder()
        val tm = manager(rec)
        tm.addTab(newWebView()) // 0
        tm.addTab(newWebView()) // 1
        tm.addTab(newWebView()) // 2
        tm.switchTo(0) // 激活 tab0（index 0）
        val activeBefore = tm.list()[tm.activeIndex]
        val resumesBefore = rec.resumed.size
        val pausesBefore = rec.paused.size

        assertTrue(tm.closeTab(2)) // index 2 > activeIndex 0

        assertEquals("激活位保持（原实现跳到被关位置）", 0, tm.activeIndex)
        assertSame("激活标签实例不变", activeBefore, tm.current())
        assertEquals("关闭后台标签不得 resume 任何 WebView（无双活跃）", resumesBefore, rec.resumed.size)
        assertEquals("被关标签 pause 恰一次（pause 单点=removed）", pausesBefore + 1, rec.paused.size)
        assertEquals(2, tm.size)
    }

    @Test
    fun closeBackgroundTabBeforeActiveShiftsActiveIndexToSameTab() {
        // 分支二（index < activeIndex）：关闭激活标签之前的后台标签——后续
        // 标签整体左移，激活位随同减一（仍指向同一标签实例）
        val rec = Recorder()
        val tm = manager(rec)
        tm.addTab(newWebView()) // 0
        tm.addTab(newWebView()) // 1
        tm.addTab(newWebView()) // 2 激活
        val activeBefore = tm.list()[2]
        val resumesBefore = rec.resumed.size

        assertTrue(tm.closeTab(0)) // index 0 < activeIndex 2

        assertEquals("激活位随左移减一（原实现跳到被关位置 0）", 1, tm.activeIndex)
        assertSame("激活标签实例不变（tab id=2 仍激活）", activeBefore, tm.current())
        assertEquals("关闭后台标签不得 resume 任何 WebView", resumesBefore, rec.resumed.size)
        assertEquals(2, tm.size)
    }

    @Test
    fun closeActiveTabResumesOnlyTheTakeoverTab() {
        // 分支三（index == activeIndex）：关闭激活标签——接管标签恢复
        // （挂起态时 resume），且只有接管标签被 resume。maxActive=2 下
        // addTab 三次后：tab0 被 LRU 挂起、tab1 被切换挂起（switchTo 离场
        // pause）、tab2 激活未挂起。
        val rec = Recorder()
        val tm = manager(rec, maxActive = 2)
        tm.addTab(newWebView()) // 0
        tm.addTab(newWebView()) // 1
        tm.addTab(newWebView()) // 2 激活——tab0 LRU 挂起，tab1 切换挂起
        assertEquals(
            setOf(0L, 1L),
            tm
                .list()
                .filter { it.suspended }
                .map { it.id }
                .toSet(),
        )
        val resumesBefore = rec.resumed.size

        assertTrue(tm.closeTab(2))

        // 接管者=tab1（挂起态）→ resume 恰一次；激活位=min(2, size-1)=1
        assertEquals("挂起态接管标签必须 resume（且仅它）", resumesBefore + 1, rec.resumed.size)
        assertEquals(1, tm.activeIndex)
        assertEquals(1L, tm.current()?.id)
        assertFalse(tm.list().first { it.id == 1L }.suspended)
        // tab0（非接管的后台标签）保持挂起，不被误恢复（双活跃回归）
        assertTrue(tm.list().first { it.id == 0L }.suspended)

        // 对照场景（maxActive=1）：仅 tab0 LRU 挂起，关闭激活 tab1 →
        // 接管者 tab0 挂起态 → resume 恰一次
        val rec2 = Recorder()
        val tm2 = manager(rec2, maxActive = 1)
        tm2.addTab(newWebView()) // 0
        tm2.addTab(newWebView()) // 1 激活——tab0 LRU 挂起
        assertEquals(
            setOf(0L),
            tm2
                .list()
                .filter { it.suspended }
                .map { it.id }
                .toSet(),
        )
        val resumesBefore2 = rec2.resumed.size
        assertTrue(tm2.closeTab(1)) // 关闭激活 tab1 → 接管者 tab0 处挂起态
        assertEquals("挂起态接管标签必须 resume", resumesBefore2 + 1, rec2.resumed.size)
        assertEquals(0, tm2.activeIndex)
        assertFalse(tm2.list().first { it.id == 0L }.suspended)
    }
}

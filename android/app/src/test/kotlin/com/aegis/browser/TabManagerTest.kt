package com.aegis.browser

import android.webkit.WebView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

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
        val suspended = tm.list().filter { it.suspended }.map { it.id }.toSet()
        assertEquals(setOf(0L, 1L), suspended)
        assertEquals(2L, tm.current()?.id) // 新增标签激活
    }
}

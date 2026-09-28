package com.aegis.browser

import android.webkit.WebView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertSame
import org.junit.Test
import org.mockito.Mockito.mock

/**
 * AD-132（审计 2026-09-23 清单·A6 批）：Tab.equals 的 WebView 引用语义守护
 * 测试——data class equals 对 webView 字段按引用比较：同一 WebView 的同字段
 * Tab 相等（StateFlow 依赖 copy-equals 感知变化）；不同 WebView 实例即使其余
 * 字段全同也不相等（标签身份随其 WebView 走）。
 */
class TabTest {
    private fun tab(webView: WebView) = Tab(id = 7L, title = "标题", url = "https://a.example", webView = webView)

    @Test
    fun sameWebViewSameFieldsAreEqual() {
        val wv = mock(WebView::class.java)
        assertEquals(tab(wv), tab(wv))
        assertEquals(tab(wv).hashCode(), tab(wv).hashCode())
    }

    @Test
    fun distinctWebViewsMakeTabsUnequalEvenWithIdenticalFields() {
        val a = tab(mock(WebView::class.java))
        val b = tab(mock(WebView::class.java))
        assertNotEquals(a, b)
    }

    @Test
    fun copyKeepsWebViewIdentity() {
        val wv = mock(WebView::class.java)
        val original = tab(wv)
        val updated = original.copy(title = "新标题", suspended = true)
        assertSame("copy 不得替换 webView 引用（导航器/注册表按实例寻址）", wv, updated.webView)
        assertNotEquals(original, updated)
    }
}

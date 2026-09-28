package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * BrowserEngine.normalizeInput JVM 单测（2026-09-24 审计——AD-021）。
 * normalizeExternal 是 SearchEngines.normalizeInput 的薄委托——本测试
 * 锁定委托关系与 DOMAIN/ABSOLUTE_URL/FORBIDDEN/SEARCH 全链行为。
 */
class BrowserEngineTest {
    @Test
    fun domainInputGetsHttpsPrefixAndLowercaseHost() {
        assertEquals("https://example.com", BrowserEngine.normalizeExternal("example.com"))
        assertEquals("https://example.com", BrowserEngine.normalizeExternal("EXAMPLE.COM"))
        assertEquals("https://example.com/path", BrowserEngine.normalizeExternal("example.com/path"))
    }

    @Test
    fun absoluteUrlIsCanonicalized() {
        assertEquals(
            "https://example.com/a?b=1",
            BrowserEngine.normalizeExternal("https://EXAMPLE.com/a?b=1"),
        )
    }

    @Test
    fun searchTermsGoToConfiguredEngine() {
        // 搜索词路径经 Uri.encode（JVM 默认值兜底不参与精确断言）——锁定引擎前缀
        val baidu = BrowserEngine.normalizeExternal("hello world")
        assertTrue(baidu!!.startsWith("https://www.baidu.com/s?wd="))
        val bing = BrowserEngine.normalizeExternal("hello world", engineKey = "bing")
        assertTrue(bing!!.startsWith("https://www.bing.com/search?q="))
        // 未知引擎 key 回退默认引擎（非法 key 不产生 null）
        val fallback = BrowserEngine.normalizeExternal("hello world", engineKey = "nonexistent")
        assertTrue(fallback!!.startsWith("https://www.baidu.com/s?wd="))
    }

    @Test
    fun forbiddenSchemesAndEmptyInputAreRejected() {
        assertNull(BrowserEngine.normalizeExternal(""))
        assertNull(BrowserEngine.normalizeExternal("javascript:alert(1)"))
        assertNull(BrowserEngine.normalizeExternal("file:///etc/passwd"))
        assertNull(BrowserEngine.normalizeExternal("data:text/html,x"))
    }

    @Test
    fun aboutBlankPassesThrough() {
        assertEquals("about:blank", BrowserEngine.normalizeExternal("about:blank"))
    }

    @Test
    fun hostWithPortClassifiesAsDomain() {
        assertEquals("https://localhost:8000", BrowserEngine.normalizeExternal("localhost:8000"))
    }
}

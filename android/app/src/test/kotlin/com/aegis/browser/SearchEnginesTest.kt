package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * 搜索归一单源自检（P0-2 / P1-1 回归——搜索功能审计 2026-09-01）。
 *
 * 覆盖纯 JVM 可测路径：classifyInput 判定 + canonicalizeExternal
 * （OriginPolicy java.net.URI）。searchUrl 的 Uri.encode 为 Android 框架
 * 类——设备上真机验证，不在 JVM 单测范围。
 */
class SearchEnginesTest {
    // ---------- classifyInput 判定 ----------

    @Test
    fun `empty input classifies as EMPTY`() {
        assertEquals(SearchEngines.InputKind.EMPTY, SearchEngines.classifyInput(""))
        assertEquals(SearchEngines.InputKind.EMPTY, SearchEngines.classifyInput("   "))
    }

    @Test
    fun `about blank is case-insensitive`() {
        assertEquals(SearchEngines.InputKind.ABOUT_BLANK, SearchEngines.classifyInput("about:blank"))
        assertEquals(SearchEngines.InputKind.ABOUT_BLANK, SearchEngines.classifyInput("ABOUT:BLANK"))
    }

    @Test
    fun `search terms with spaces classify as SEARCH`() {
        assertEquals(SearchEngines.InputKind.SEARCH, SearchEngines.classifyInput("今天天气"))
        assertEquals(SearchEngines.InputKind.SEARCH, SearchEngines.classifyInput("rust uniffi"))
    }

    @Test
    fun `dotted input without spaces classifies as DOMAIN`() {
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("baidu.com"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("www.example.org"))
    }

    @Test
    fun `trailing dot is not a domain (search fallback)`() {
        assertEquals(SearchEngines.InputKind.SEARCH, SearchEngines.classifyInput("weather."))
    }

    @Test
    fun `http https are absolute urls`() {
        assertEquals(SearchEngines.InputKind.ABSOLUTE_URL, SearchEngines.classifyInput("https://www.baidu.com"))
        assertEquals(SearchEngines.InputKind.ABSOLUTE_URL, SearchEngines.classifyInput("http://example.com/a"))
    }

    @Test
    fun `non-navigation schemes are FORBIDDEN (fail closed)`() {
        // P0-1 补丁对齐：file:/javascript:/data: 等绝不补 https:// 拼接
        assertEquals(
            SearchEngines.InputKind.FORBIDDEN_SCHEME,
            SearchEngines.classifyInput("file:///C:/Windows/win.ini"),
        )
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("javascript:alert(1)"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("data:text/html,<b>x</b>"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("vbscript:msgbox(1)"))
    }

    @Test
    fun `host with port classifies as DOMAIN (T1 regression)`() {
        // T1 修复（全面审计批次2）：字母开头的 host:port（localhost:8000）
        // 此前被 SCHEME_PREFIX 匹配成 scheme → FORBIDDEN。数字开头的
        // 192.168.1.1:8080 原本就不匹配 scheme 正则（首字符限定字母）——
        // 一并列断言锁最终行为。
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("localhost:8000"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("192.168.1.1:8080"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("example.com:8080/path"))
        // 全链路：host:port → https 补全 + 端口保留
        assertEquals("https://localhost:8000", SearchEngines.canonicalizeExternal("https://localhost:8000"))
    }

    @Test
    fun `scheme-like words with portless colon stay FORBIDDEN`() {
        // 端口段非数字 → 仍按真 scheme 处理（fail-closed 不回退）
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("localhost:abc"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("javascript:alert(1)"))
    }

    // ---------- normalizeInput 全链路 ----------

    @Test
    fun `search term goes through (no android Uri in JVM - delegate check via classify)`() {
        // searchUrl 依赖 android.net.Uri——JVM 上不可执行；判定正确性由
        // classifyInput 保证，这里只验证 FORBIDDEN/空输入的拒绝路径
        assertNull(SearchEngines.normalizeInput("javascript:alert(1)", "baidu"))
        assertNull(SearchEngines.normalizeInput("file:///etc/passwd", "baidu"))
        assertNull(SearchEngines.normalizeInput("   ", "baidu"))
        assertNull(SearchEngines.normalizeInput("", "baidu"))
    }

    @Test
    fun `absolute url canonicalizes with lowercase host`() {
        assertEquals(
            "https://www.baidu.com/s?wd=x",
            SearchEngines.canonicalizeExternal("https://WWW.BAIDU.COM/s?wd=x"),
        )
    }

    @Test
    fun `absolute url with space is percent-encoded then accepted`() {
        // D-1 对齐：完整 URL 空格 → %20（浏览器惯例），不再被空白拒绝
        assertEquals(
            "https://example.net/a%20b",
            SearchEngines.canonicalizeExternal("https://example.net/a b"),
        )
    }

    @Test
    fun `domain is https-prefixed and canonicalized`() {
        assertEquals(
            "https://example.com",
            SearchEngines.canonicalizeExternal("https://example.com"),
        )
    }

    @Test
    fun `invalid domain rejected by origin policy`() {
        assertNull(SearchEngines.canonicalizeExternal("https://"))
    }
}

package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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

    // ---------- AD-119（审计 2026-09-23 清单·A6 批）：大写 scheme 分类 ----------

    @Test
    fun `uppercase http https classify as absolute urls`() {
        // scheme 判定大小写不敏感（与 OriginPolicy/https 升级层同口径）
        assertEquals(SearchEngines.InputKind.ABSOLUTE_URL, SearchEngines.classifyInput("HTTPS://WWW.BAIDU.COM"))
        assertEquals(SearchEngines.InputKind.ABSOLUTE_URL, SearchEngines.classifyInput("Http://Example.COM/a"))
    }

    @Test
    fun `uppercase forbidden schemes stay FORBIDDEN`() {
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("JAVASCRIPT:alert(1)"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("File:///C:/win.ini"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("DATA:text/html,x"))
    }

    @Test
    fun `uppercase absolute url canonicalizes with lowercase host`() {
        // 大写 scheme + 大写 host → 归一后 scheme 保留、host 小写
        assertEquals("http://example.com", SearchEngines.normalizeInput("HTTP://EXAMPLE.COM", "baidu"))
        assertEquals(
            "https://example.com/a?b=1",
            SearchEngines.normalizeInput("HTTPS://EXAMPLE.COM/a?b=1", "baidu"),
        )
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

    // ------- AD-031（2026-09-24 审计）：normalizeInput DOMAIN 全链补强 -------
    @Test
    fun `normalizeInput domain full chain lowercases host`() {
        assertEquals("https://example.com", SearchEngines.normalizeInput("EXAMPLE.COM", "baidu"))
        assertEquals("https://example.com/path", SearchEngines.normalizeInput("ExAmPlE.CoM/path", "baidu"))
    }

    @Test
    fun `normalizeInput domain full chain preserves path query fragment`() {
        assertEquals(
            "https://example.com/a/b?c=1#f",
            SearchEngines.normalizeInput("example.com/a/b?c=1#f", "baidu"),
        )
    }

    @Test
    fun `normalizeInput domain full chain preserves explicit port`() {
        assertEquals("https://example.com:8443/x", SearchEngines.normalizeInput("example.com:8443/x", "baidu"))
    }

    @Test
    fun `normalizeInput domain with space becomes search`() {
        // 含空格的「域名形态」输入必须降级为搜索词（不得当域名拼接）
        val out = SearchEngines.normalizeInput("example com", "baidu")
        assertTrue(out!!.startsWith("https://www.baidu.com/s?wd="))
    }

    @Test
    fun `normalizeInput about blank passes through unchanged`() {
        assertEquals("about:blank", SearchEngines.normalizeInput("ABOUT:BLANK", "baidu"))
    }

    @Test
    fun `normalizeInput rejects empty and forbidden schemes`() {
        assertNull(SearchEngines.normalizeInput("", "baidu"))
        assertNull(SearchEngines.normalizeInput("   ", "baidu"))
        assertNull(SearchEngines.normalizeInput("javascript:alert(1)", "baidu"))
        assertNull(SearchEngines.normalizeInput("file:///etc/passwd", "baidu"))
    }

    // ---------- AD-057（2026-09-24 审计）：searchUrl/uriEncode 纯字符串化 ----------
    @Test
    fun `uriEncode keeps unreserved characters and slash`() {
        assertEquals("helloworld", SearchEngines.uriEncode("helloworld"))
        assertEquals("a/b", SearchEngines.uriEncode("a/b"))
        // AD-248（2026-09-26 审计）：AOSP Uri.encode 固有放行集是 "_-!.~'()*"
        // （含 '!'——isAllowed 源码实证）；旧断言把 '!' 编码为 %21 与平台语义
        // 不一致（完整对照矩阵见 androidTest/SearchEnginesUriEncodeInstrumentedTest）
        assertEquals("a.b-c_d~e'f(g)h*i!j", SearchEngines.uriEncode("a.b-c_d~e'f(g)h*i!j"))
    }

    @Test
    fun `uriEncode percent-encodes space plus and cjk as uppercase utf8`() {
        assertEquals("hello%20world", SearchEngines.uriEncode("hello world"))
        // '+' 不是 unreserved（与 Uri.encode(text, "/") 语义一致）
        assertEquals("rust%20%2B%20uniffi", SearchEngines.uriEncode("rust + uniffi"))
        assertEquals("%E4%B8%AD%E6%96%87", SearchEngines.uriEncode("中文"))
        assertEquals("100%25", SearchEngines.uriEncode("100%"))
    }

    @Test
    fun `searchUrl appends encoded query on known and default engine`() {
        assertEquals("https://www.baidu.com/s?wd=rust%20uniffi", SearchEngines.searchUrl("rust uniffi", "baidu"))
        assertEquals("https://www.bing.com/search?q=%E4%B8%AD", SearchEngines.searchUrl("中", "bing"))
        // 未知引擎 key 回退默认引擎
        assertEquals(
            "https://www.baidu.com/s?wd=x",
            SearchEngines.searchUrl("x", "no-such-engine"),
        )
    }

    @Test
    fun `normalizeInput search path is now jvm-testable end to end`() {
        // AD-057 前搜索链路在 JVM 只能测 classify——现在全链可断言
        assertEquals(
            "https://www.baidu.com/s?wd=today%20weather",
            SearchEngines.normalizeInput("today weather", "baidu"),
        )
    }

    // ---------- AD-146（审计 2026-09-23 清单·A6 批）：ENGINE_NAMES 单源守护 ----------

    @Test
    fun `engine names keys exactly match engine urls`() {
        // 显示名表收敛 SearchEngines 单源（AegisHomeBridge 消费）——键集与
        // ENGINE_URLS 漂移（加引擎漏登记名）在此失败
        assertEquals(SearchEngines.ENGINE_URLS.keys, SearchEngines.ENGINE_NAMES.keys)
        SearchEngines.ENGINE_NAMES.forEach { (key, name) ->
            assertTrue("显示名不得为空: $key", name.isNotBlank())
        }
    }

    // ---------- AD-166（审计 2026-09-23 清单·A7 批）：scheme 字符集边界 ----------

    @Test
    fun `scheme charset sub-delims classify as forbidden`() {
        // RFC 3986 scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
        // 含 + - 的合法 scheme 形态可被识别；非 http/https 一律 fail-closed
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("my+app://x"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("my-app://x"))
        // 含点的 prefix 必为 host（T1：真 scheme 永不含点）→ 域名裁决
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("my.app://x"))
    }

    @Test
    fun `digit leading pseudo scheme is not a scheme`() {
        // scheme 必须字母开头——"1http:" 不满足 ALPHA 开头，regex 不匹配 →
        // 走无 scheme 分支（按 looksLikeUrl/搜索词裁决，绝不进 FORBIDDEN 误报）
        assertEquals(SearchEngines.InputKind.SEARCH, SearchEngines.classifyInput("1http://x"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("1http://x.y"))
    }

    @Test
    fun `scheme with dot falls back to url heuristics`() {
        // 真 scheme 永不含点；prefix 含点必为 host（T1 语义）——
        // `a.b:...` 按域名/搜索词裁决而非 scheme 判定
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("a.b:path"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("a.b"))
    }

    @Test
    fun `scheme charset rejects illegal chars by not matching`() {
        // 下划线不在 scheme 字符集——"my_app:x" 的 prefix 匹配中断于 '_' 且
        // 不足到冒号 → 无 scheme 匹配 → 走 looksLikeUrl（无点）→ 搜索词
        assertEquals(SearchEngines.InputKind.SEARCH, SearchEngines.classifyInput("my_app:x"))
        // 含点形态转域名裁决（T1 语义）
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("my_app:x.y"))
    }

    // ---------- AD-167（审计 2026-09-23 清单·A7 批）：isPortSegment 边界 ----------

    @Test
    fun `host with port segment boundaries classify as domain`() {
        // 端口段语义：首个 '/' 前 1-5 位纯数字（TCP 端口上限 5 位）即 host:port
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("localhost:1"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("localhost:0"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("localhost:65535"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("localhost:65536"))
        assertEquals(SearchEngines.InputKind.DOMAIN, SearchEngines.classifyInput("localhost:12345/path"))
    }

    @Test
    fun `host with overlong or non numeric port is not host port form`() {
        // 6 位数字超端口段上限 → 非 host:port 形态（真 scheme 判定继续：
        // "localhost" 非 http/https scheme → FORBIDDEN fail-closed）
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("localhost:123456"))
        // 空端口段（"localhost:"）与字母端口段同判
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("localhost:"))
        assertEquals(SearchEngines.InputKind.FORBIDDEN_SCHEME, SearchEngines.classifyInput("localhost:80a"))
    }
}

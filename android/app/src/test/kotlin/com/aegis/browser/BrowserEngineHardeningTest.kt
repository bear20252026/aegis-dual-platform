package com.aegis.browser

import android.app.Application
import android.webkit.CookieManager
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * AD-055（2026-09-24 审计）：BrowserEngine.configure() 12 项硬化标志零回归——
 * WebSettings 属性在 returnDefaultValues 桩下全为默认值（JVM 单测无法断言
 * 真值），改用 Robolectric 真实 shadow 逐项断言。任一硬化标志被无意放宽
 * （如 allowFileAccess 改回 true）即在此失败。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class BrowserEngineHardeningTest {
    private val webView: WebView = WebView(ApplicationProvider.getApplicationContext<Application>())

    @Test
    fun configureAppliesAllHardeningFlags() {
        BrowserEngine(webView).configure()
        val s = webView.settings
        // 功能面（有意开启的两项）
        assertTrue(s.javaScriptEnabled)
        assertTrue(s.domStorageEnabled)
        // 文件/内容访问全关（file:// 攻击面）
        assertFalse(s.allowFileAccess)
        assertFalse(s.allowContentAccess)
        assertFalse(s.allowFileAccessFromFileURLs)
        assertFalse(s.allowUniversalAccessFromFileURLs)
        // 混合内容绝不放行（明文子资源）
        assertEquals(WebSettings.MIXED_CONTENT_NEVER_ALLOW, s.mixedContentMode)
        // 弹窗/多窗口关闭
        assertFalse(s.javaScriptCanOpenWindowsAutomatically)
        assertFalse(s.supportMultipleWindows())
        // 媒体不自动播放（safeBrowsingEnabled 同为 configure() 显式置 true，
        // 但 Robolectric ShadowWebSettings 未实现该 getter（恒 false）——无法
        // 在 JVM 侧断言，真机回归覆盖）
        assertTrue(s.mediaPlaybackRequiresUserGesture)
        // 移动端渲染适配（viewport/缩放）
        assertTrue(s.useWideViewPort)
        assertTrue(s.loadWithOverviewMode)
        assertTrue(s.builtInZoomControls)
        assertFalse(s.displayZoomControls)
    }

    @Test
    fun thirdPartyCookiesAreRejectedAfterConfigure() {
        BrowserEngine(webView).configure()
        // A-03：默认限制第三方 Cookie（防跨站追踪）
        assertFalse(CookieManager.getInstance().acceptThirdPartyCookies(webView))
    }

    // ---------------- AD-165（审计 2026-09-23 清单·A7 批）：标题 256 截断 ----------------

    /** 经 ArgumentCaptor 捕获 configure() 注入的 WebChromeClient（spy 真实
     *  WebView——configure 的 settings 链需要真实 shadow 实现）。 */
    private fun chromeClientOf(engineWebView: WebView): android.webkit.WebChromeClient {
        val captor = org.mockito.ArgumentCaptor.forClass(android.webkit.WebChromeClient::class.java)
        org.mockito.Mockito
            .verify(engineWebView)
            .webChromeClient = captor.capture()
        return captor.value
    }

    @Test
    fun receivedTitleIsTruncatedTo256Chars() {
        // 标题是远端可控输入：Tab.title 进 StateFlow → 标签栏渲染，超长标题
        // 此前无截断守护。锁定 onReceivedTitle 经 MAX_TITLE_LENGTH（256）截断。
        val spyView = org.mockito.Mockito.spy(webView)
        var observed: String? = null
        BrowserEngine(spyView, onTitleObserved = { observed = it }).configure()
        val chromeClient = chromeClientOf(spyView)
        val longTitle = "阿".repeat(1000)
        chromeClient.onReceivedTitle(spyView, longTitle)
        assertEquals("标题必须截断到 256 字符（UTF-16 char 计）", 256, observed!!.length)
    }

    @Test
    fun receivedNullTitleYieldsEmptyString() {
        val spyView = org.mockito.Mockito.spy(webView)
        var observed: String? = null
        BrowserEngine(spyView, onTitleObserved = { observed = it }).configure()
        val chromeClient = chromeClientOf(spyView)
        chromeClient.onReceivedTitle(spyView, null)
        assertEquals("", observed)
    }
}

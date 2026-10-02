package com.aegis.browser

import android.webkit.ValueCallback
import android.webkit.WebView
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.ArgumentMatchers.any
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when` as whenever

/**
 * AD-126/127（审计 2026-09-23 清单·A6 批）：ReaderController 状态机单测——
 * toggle 提取成功回填/失败提示/关闭清空三态，translate 各失败分支
 * （无 URL / 非 http 页 / 导航被拒）与成功静默。WebView 经 mockito 注入
 * evaluateJavascript 同步回调（returnDefaultValues 桩下回调默认不触发）。
 */
class ReaderControllerTest {
    private val alerts = mutableListOf<Int>()

    /** 构建 evaluateJavascript 同步回吐 [payload] 的 WebView 桩。 */
    private fun webViewYielding(payload: String?): WebView =
        mock(WebView::class.java).also { wv ->
            whenever(wv.evaluateJavascript(anyString(), any<ValueCallback<String>?>()))
                .thenAnswer { invocation ->
                    @Suppress("UNCHECKED_CAST")
                    (invocation.getArgument(1) as ValueCallback<String>?)?.onReceiveValue(payload)
                    null
                }
        }

    private fun controller(
        webView: WebView? = null,
        url: String? = null,
        navigateResult: Boolean = true,
        navigations: MutableList<String> = mutableListOf(),
    ): ReaderController =
        ReaderController(
            currentWebView = { webView },
            currentUrl = { url },
            navigateExternal = { target ->
                navigations.add(target)
                navigateResult
            },
            alertRes = { alerts.add(it) },
        )

    private fun payload(
        ok: Boolean,
        title: String = "标题",
        text: String = "正文内容",
    ): String {
        val obj = JSONObject()
        obj.put("ok", ok)
        obj.put("title", title)
        obj.put("text", text)
        return obj.toString()
    }

    // ---------------------------------------------------------------- AD-126

    @Test
    fun toggleWithExtractedContentFillsState() {
        val controller = controller(webView = webViewYielding(payload(ok = true)))
        assertNull(controller.content.value)
        controller.toggleReaderMode()
        assertEquals("标题", controller.content.value!!.title)
        assertEquals("正文内容", controller.content.value!!.text)
        assertTrue("提取成功不得弹提示", alerts.isEmpty())
    }

    @Test
    fun toggleWithoutContentAlertsAndKeepsStateNull() {
        val controller = controller(webView = webViewYielding(payload(ok = false)))
        controller.toggleReaderMode()
        assertNull(controller.content.value)
        assertEquals(listOf(R.string.reader_no_content), alerts)
    }

    @Test
    fun toggleWithoutWebViewAlertsInsteadOfCrashing() {
        val controller = controller(webView = null)
        controller.toggleReaderMode()
        assertNull(controller.content.value)
        assertEquals(listOf(R.string.reader_no_content), alerts)
    }

    @Test
    fun dismissClearsContent() {
        val controller = controller(webView = webViewYielding(payload(ok = true)))
        controller.toggleReaderMode()
        assertEquals("标题", controller.content.value!!.title)
        controller.dismissReader()
        assertNull(controller.content.value)
    }

    // --------------------------------------------- AD-267（2026-10-01 审计）

    @Test
    fun staleExtractionCallbackIsDroppedAfterTabSwitch() {
        // evaluateJavascript 回填归属校验：提取发起后切标签，旧正文不得写入
        // 新语境（回调落地时 currentWebView 已非发起时实例）
        var current: WebView? = null
        var deferred: ValueCallback<String>? = null
        val origin =
            mock(WebView::class.java).also { wv ->
                whenever(wv.evaluateJavascript(anyString(), any<ValueCallback<String>?>()))
                    .thenAnswer { invocation ->
                        deferred = invocation.getArgument(1) as ValueCallback<String>
                        null
                    }
            }
        current = origin
        val controller =
            ReaderController(
                currentWebView = { current },
                currentUrl = { "https://a.example" },
                navigateExternal = { true },
                alertRes = { alerts.add(it) },
            )
        controller.toggleReaderMode()
        // 提取挂起期间切换标签（currentWebView 指向新实例）
        current = mock(WebView::class.java)
        deferred?.onReceiveValue(payload(ok = true))
        assertNull("切换后旧正文不得入新语境（AD-267）", controller.content.value)
        assertTrue("过期回调不弹提示（新标签语境下提示同样错位）", alerts.isEmpty())
    }

    @Test
    fun freshExtractionCallbackStillFillsContent() {
        // 对照组：未切标签时同一异步回填路径正常写状态（归属校验不误伤）
        var current: WebView? = null
        var deferred: ValueCallback<String>? = null
        val origin =
            mock(WebView::class.java).also { wv ->
                whenever(wv.evaluateJavascript(anyString(), any<ValueCallback<String>?>()))
                    .thenAnswer { invocation ->
                        deferred = invocation.getArgument(1) as ValueCallback<String>
                        null
                    }
            }
        current = origin
        val controller =
            ReaderController(
                currentWebView = { current },
                currentUrl = { "https://a.example" },
                navigateExternal = { true },
                alertRes = { alerts.add(it) },
            )
        controller.toggleReaderMode()
        deferred?.onReceiveValue(payload(ok = true))
        assertEquals("标题", controller.content.value!!.title)
        assertTrue(alerts.isEmpty())
    }

    // ---------------------------------------------------------------- AD-127

    @Test
    fun translateWithoutUrlAlertsAndNeverNavigates() {
        val navigations = mutableListOf<String>()
        val controller = controller(url = null, navigations = navigations)
        controller.translateCurrentPage()
        assertTrue("无 URL 不得发起导航", navigations.isEmpty())
        assertEquals(listOf(R.string.translate_unavailable), alerts)
    }

    @Test
    fun translateOnLocalPageAlertsWithoutNavigating() {
        val navigations = mutableListOf<String>()
        val controller = controller(url = "file:///android_asset/start.html", navigations = navigations)
        controller.translateCurrentPage()
        assertTrue("本地壳页不外发翻译", navigations.isEmpty())
        assertEquals(listOf(R.string.translate_unavailable), alerts)
    }

    @Test
    fun translateDeniedByPolicyAlerts() {
        val navigations = mutableListOf<String>()
        val controller =
            controller(url = "https://example.com/a", navigateResult = false, navigations = navigations)
        controller.translateCurrentPage()
        assertEquals(1, navigations.size)
        assertTrue("翻译目标须为翻译服务地址", navigations[0].startsWith("https://www.translatetheweb.com/"))
        assertEquals(listOf(R.string.translate_unavailable), alerts)
    }

    @Test
    fun translateSuccessIsSilent() {
        val navigations = mutableListOf<String>()
        val controller =
            controller(url = "https://example.com/a", navigateResult = true, navigations = navigations)
        controller.translateCurrentPage()
        assertEquals(1, navigations.size)
        assertTrue("导航成功不得弹提示", alerts.isEmpty())
    }
}

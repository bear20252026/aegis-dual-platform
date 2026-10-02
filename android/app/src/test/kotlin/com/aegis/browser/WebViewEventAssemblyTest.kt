package com.aegis.browser

import android.app.Application
import android.net.Uri
import android.net.http.SslError
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import androidx.test.core.app.ApplicationProvider
import com.aegis.broker.AndroidBroker
import com.aegis.broker.Decision
import com.aegis.webviewadapter.WebViewErrorCodes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mockito.mock
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.time.Clock
import org.mockito.Mockito.`when` as whenever

/**
 * AD-332（2026-10-02 审计）：WebViewEventAssembly 装配回调回归——179 行
 * 事件装配体此前零测试（URL 展示归一/标题截断/错误面板文案路由/标签归属
 * 清除只能靠真机走查）。Robolectric 真实 WebView 创建链 + 假 Host 记录
 * 状态写入，驱动 WebViewClient/WebChromeClient 回调逐面断言。
 *
 * 桩口径：AndroidBroker mockito inline mock（registerSession 放行；
 * updateDocumentGeneration/evaluateNavigation 按用例桩定），WebView 经
 * SecureWebViewFactory 真实创建（导航器注册表真实接线）。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WebViewEventAssemblyTest {
    private lateinit var broker: AndroidBroker
    private lateinit var tm: TabManager
    private lateinit var host: RecordingHost
    private lateinit var webView: WebView
    private lateinit var client: android.webkit.WebViewClient
    private lateinit var chromeClient: android.webkit.WebChromeClient

    /** 假 Host：记录装配点的全部状态写入（AD-332）。 */
    private class RecordingHost(
        private val tabManager: () -> TabManager?,
    ) : WebViewEventAssembly.Host {
        val addresses = mutableListOf<String>()
        val alerts = mutableListOf<String>()
        val errors = mutableListOf<PageError>()
        var clearErrorCount = 0
        var refreshCount = 0
        var downloadConfirmationCount = 0

        override val activeTabManager: TabManager?
            get() = tabManager()

        override val isAddressDraftActive: Boolean = false

        // detekt-修复（2026-10-02 审计云端实证）：MaxLineLength>120——if-else 加花括号拆行
        // （ktlint expression-body 会回收单行可容纳的折行——花括号块不回收，结构稳定）
        override fun displayAddress(url: String): String =
            if (url.startsWith("file://")) {
                BrowserViewModel.HOME_DISPLAY_URL
            } else {
                url
            }

        override fun submitPageAddress(url: String) {
            addresses.add(url)
        }

        override fun submitPageError(error: PageError) {
            errors.add(error)
        }

        override fun clearPageError() {
            clearErrorCount++
        }

        override fun submitWebViewAlert(text: String) {
            alerts.add(text)
        }

        override fun refreshTabs() {
            refreshCount++
        }

        // detekt-修复（2026-10-02 审计云端实证）：MaxLineLength>120——实参折行（ktlint 不回收已折行实参）。
        override fun errorStrings(): PageErrorTexts.Strings =
            pageErrorStringsOf(
                { id -> "res($id)" },
                { id, arg -> "res($id,$arg)" },
            )

        override fun requestDownloadConfirmation(
            webView: WebView,
            url: String,
            proceed: () -> Unit,
        ) {
            downloadConfirmationCount++
        }
    }

    @Before
    fun setUp() {
        broker = mock(AndroidBroker::class.java)
        whenever(
            broker.registerSession(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
            ),
        ).thenReturn(true)
        whenever(
            broker.updateDocumentGeneration(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
            ),
        ).thenReturn(true)
        tm = TabManager()
        host = RecordingHost { tm }
        val assembly =
            WebViewEventAssembly(
                broker = broker,
                host = host,
                onRendererGone = {},
                onConfirmationRequested = { _, _ -> },
                onConfirmationResolved = { },
            )
        webView = assembly.create(ApplicationProvider.getApplicationContext<Application>())
        tm.addTab(webView, url = "https://start.example/")
        client = webView.webViewClient
        chromeClient = webView.webChromeClient!!
    }

    // ---------------- URL 展示归一（AD-063 口径经装配面回归） ----------------

    @Test
    fun onPageStartedSubmitsNormalizedDisplayAddress() {
        // file:// 壳页 URL 上抛为 aegis://home 占位（不泄露内部路径结构）
        client.onPageStarted(webView, "file:///android_asset/start.html", null)
        assertEquals(listOf(BrowserViewModel.HOME_DISPLAY_URL), host.addresses)
        // 普通远程 URL 原样上抛
        client.onPageStarted(webView, "https://example.com/page", null)
        assertEquals(
            listOf(BrowserViewModel.HOME_DISPLAY_URL, "https://example.com/page"),
            host.addresses,
        )
    }

    @Test
    fun onPageStartedRechecksRedirectTargetAgainstPolicy() {
        // AD-256：302 重定向复核——Allow 放行并观察 URL
        whenever(
            broker.evaluateNavigation(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.eq("https://example.com/redirected"),
                org.mockito.ArgumentMatchers.anyString(),
            ),
        ).thenReturn(Decision.Allow(stubAction()))
        client.onPageStarted(webView, "https://example.com/redirected", null)
        assertEquals(listOf("https://example.com/redirected"), host.addresses)
    }

    // ---------------- 标题截断（超长标题不进标签数据层） ----------------

    @Test
    fun onReceivedTitleTruncatesToCharBoundaryLimit() {
        chromeClient.onReceivedTitle(webView, "T".repeat(300))
        assertEquals(256, tm.current()?.title?.length)
        assertTrue("标题回填后必须刷新标签列表", host.refreshCount >= 1)
    }

    // ---------------- 错误面板文案路由（AD-035 结构 → 文案映射） ----------------

    @Test
    fun onReceivedErrorRoutesMainFrameErrorTextOnly() {
        val error = mock(WebResourceError::class.java)
        whenever(error.errorCode).thenReturn(-2)
        whenever(error.description).thenReturn("host lookup")

        // 子框架错误：静默（不遮蔽整页）
        client.onReceivedError(webView, fakeRequest("https://ads.example/f.js", isMainFrame = false), error)
        assertTrue(host.errors.isEmpty())

        // 主框架错误：经 PageErrorTexts 路由（errorStrings 假实现可辨识）
        client.onReceivedError(webView, fakeRequest("https://example.com/x", isMainFrame = true), error)
        assertEquals(1, host.errors.size)
        assertEquals(
            PageErrorTexts.textFor(WebViewErrorCodes.ERROR_MAIN_FRAME, "-2:host lookup", host.errorStrings()),
            host.errors.first().description,
        )
        assertEquals(false, host.errors.first().isSsl)
    }

    @Test
    fun sslErrorOnMainFrameRoutesSslPanelText() {
        val handler = mock(android.webkit.SslErrorHandler::class.java)
        val sslError = mock(SslError::class.java)
        whenever(sslError.url).thenReturn("https://example.com/")
        whenever(sslError.primaryError).thenReturn(3)
        webView.loadUrl("https://example.com/") // view.url 与 error.url 归属一致

        client.onReceivedSslError(webView, handler, sslError)

        assertEquals(1, host.errors.size)
        assertEquals(
            PageErrorTexts.textFor(WebViewErrorCodes.ERROR_SSL_CERTIFICATE, "3", host.errorStrings()),
            host.errors.first().description,
        )
        assertEquals(true, host.errors.first().isSsl)
    }

    // ---------------- 标签归属：错误只挂当前标签 / 新页面开始清除 ----------------

    @Test
    fun errorFromBackgroundTabIsNotSurfaced() {
        // 第二个标签成为当前——第一标签（后台）的错误不上屏
        val backgroundClient = client
        tm.addTab(mock(WebView::class.java).also { whenever(it.url).thenReturn(null) }, url = "https://two.example/")
        val error = mock(WebResourceError::class.java)
        whenever(error.errorCode).thenReturn(-2)
        whenever(error.description).thenReturn("down")
        backgroundClient.onReceivedError(
            webView,
            fakeRequest("https://start.example/fail", isMainFrame = true),
            error,
        )
        assertTrue("后台标签错误不得上屏", host.errors.isEmpty())
    }

    @Test
    fun newPageStartClearsErrorPanelForCurrentTab() {
        val error = mock(WebResourceError::class.java)
        whenever(error.errorCode).thenReturn(-2)
        whenever(error.description).thenReturn("down")
        client.onReceivedError(webView, fakeRequest("https://start.example/fail", isMainFrame = true), error)
        assertEquals(1, host.errors.size)
        val clearsBefore = host.clearErrorCount
        client.onPageStarted(webView, "https://example.com/next", null)
        assertTrue("当前标签新页面开始必须清除错误面板", host.clearErrorCount > clearsBefore)
    }

    // ---------------- AD-331：二级下载确认经宿主上抛 ----------------

    @Test
    fun downloadConfirmationRequestReachesHost() {
        // detekt-修复（2026-10-02 审计云端实证）：删除未用局部 context（ApplicationProvider
        // 取值后无人引用——robolectric 假 Host 不触 UI 上下文）
        // 查询参数携带危险扩展（二级）——非 http(s) 前置拦截不会触发；
        // 直接驱动下载监听（工厂接线面）
        val listener = shadowOf(webView).getDownloadListener()
        assertNotNull("工厂必须注册 DownloadListener", listener)
        listener.onDownloadStart(
            "https://evil.example/dl?file=x.exe",
            "ua",
            "attachment; filename=\"report.pdf\"",
            "application/octet-stream",
            10L,
        )
        assertEquals("二级下载确认必须上抛宿主", 1, host.downloadConfirmationCount)
    }

    // ---------------- 辅助 ----------------

    private fun stubAction() =
        com.aegis.broker.AuthorizedAction(
            sessionId = "stub-session",
            tabId = "stub-tab",
            documentGeneration = 0,
            origin = "https://example.com",
            method = "GET",
            canonicalParameters = "/",
            scope = "navigation",
            expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("120s")),
            nonce = "stub-nonce",
            policyVersion = "1.0",
        )

    private fun fakeRequest(
        url: String,
        isMainFrame: Boolean,
    ): WebResourceRequest {
        val uri = mock(Uri::class.java)
        whenever(uri.toString()).thenReturn(url)
        val request = mock(WebResourceRequest::class.java)
        whenever(request.url).thenReturn(uri)
        whenever(request.isForMainFrame).thenReturn(isMainFrame)
        return request
    }

    private fun shadowOf(wv: WebView) = org.robolectric.Shadows.shadowOf(wv)
}

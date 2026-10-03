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
import com.aegis.broker.DenyReason
import com.aegis.webviewadapter.WebViewErrorCodes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mockito.mock
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
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
        // AD-256：302 落地复核——Deny 即顶层上抛 + 阻断 URL 不得进地址栏
        // （Allow 放行观察面已由 onPageStartedSubmitsNormalizedDisplayAddress 覆盖。
        //   桩形全仓放行口径：纯 any 系——eq 混桩对 Kotlin 非空参数求值为 null，
        //   本工具链恒 NPE 且脏 matcher 栈级联污染下一用例）
        whenever(
            broker.evaluateNavigation(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
            ),
        ).thenReturn(Decision.Deny(DenyReason("url_policy", "拒绝重定向 URL")))
        client.onPageStarted(webView, "https://example.com/redirected", null)
        assertTrue("被拒重定向不得上抛地址栏", host.addresses.isEmpty())
        // 审计第六轮（2026-10-03）：旧断言与装配点同式（都写死 1 参 text）——
        // 是恒等式而非期望，看不见「%1$s 原样上屏、code 丢失」这个缺陷。
        // 现锚定渲染单源 denyAlertText，并直接断 code 出现在提示文案里。
        assertEquals(
            "顶层拒绝必须上抛安全提示（deny code 作格式化实参带出）",
            listOf(PageErrorTexts.denyAlertText("url_policy", host.errorStrings())),
            host.alerts,
        )
        assertTrue("提示文案必须带出 deny code：${host.alerts}", host.alerts.single().contains("url_policy"))
    }

    @Test
    fun denyAlertRendersCodeWithoutRawPlaceholder() {
        // 审计第六轮（2026-10-03）：真实资源表渲染回归——nav_rejected_code 声明
        // %1$s，装配点旧形态走 1 参 getString：用户字面看到「…（%1$s）」，
        // 拒绝原因（code）永不现形。假 Strings 只能验「实参有传」，占位符
        // 是否真被替换必须经 Robolectric 的 AAPT 资源表判定。
        val ctx = ApplicationProvider.getApplicationContext<android.content.Context>()
        val realStrings =
            pageErrorStringsOf(
                text = { id -> ctx.getString(id) },
                textWithArg = { id, arg -> ctx.getString(id, arg) },
            )
        val rendered = PageErrorTexts.denyAlertText("navigation_not_consumed", realStrings)
        assertTrue("渲染文案必须带出 deny code：$rendered", rendered.contains("navigation_not_consumed"))
        assertFalse("渲染文案不得残留原始占位符：$rendered", rendered.contains("%1"))
        // 专有条目（session_expired 无占位符）不因带实参而变形
        assertEquals(
            ctx.getString(R.string.session_expired),
            PageErrorTexts.denyAlertText("session_expired", realStrings),
        )
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

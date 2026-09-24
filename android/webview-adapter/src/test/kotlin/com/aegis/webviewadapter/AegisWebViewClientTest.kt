package com.aegis.webviewadapter

import android.net.Uri
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import com.aegis.broker.AndroidBroker
import com.aegis.broker.AuthorizedAction
import com.aegis.broker.Decision
import com.aegis.broker.DenyReason
import kotlinx.datetime.Clock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.mock
import org.mockito.Mockito.never
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when` as whenever

/**
 * AegisWebViewClient 导航授权状态机 JVM 单测（2026-09-24 审计批次 A2——AD-007..015）。
 *
 * 前置（与 AD-002 同一 JVM 可测化先例）：
 * - scheme 判定/https 升级已纯字符串化（schemePrefixOf——不依赖 android.net.Uri）；
 * - android.util.Log 经 unitTests.returnDefaultValues 兜底；
 * - AndroidBroker/WebView/WebResourceRequest/RenderProcessGoneDetail 经
 *   mockito 5 inline mock（final 类可 mock）。
 *
 * 覆盖：AD-008 合法 https 放行 ｜ AD-009 顶层拒绝上抛 ｜ AD-010 主框架 http
 * 阻断+升级 ｜ AD-011 iframe http 不劫持顶层 ｜ AD-012 onRenderProcessGone
 * 返回 true ｜ AD-013 close() 销毁 Broker 会话 ｜ AD-014 大写 scheme 升级 ｜
 * AD-015 approvePendingNavigation 空边界。
 */
class AegisWebViewClientTest {
    private lateinit var broker: AndroidBroker
    private lateinit var view: WebView
    private val deniedCodes = mutableListOf<String>()

    private val allowAction =
        AuthorizedAction(
            sessionId = SESSION,
            tabId = TAB,
            documentGeneration = 0,
            origin = "https://example.com",
            method = "GET",
            canonicalParameters = "/",
            scope = "navigation",
            expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("120s")),
            nonce = "test-nonce",
            policyVersion = "1.0",
        )

    private companion object {
        const val SESSION = "session-1"
        const val TAB = "tab-1"
    }

    @Before
    fun setUp() {
        broker = mock(AndroidBroker::class.java)
        view = mock(WebView::class.java)
        whenever(broker.renewSession(SESSION, TAB)).thenReturn(true)
    }

    private fun newClient(
        requireConfirmation: Boolean = false,
        onRendererGone: (WebView) -> Unit = {},
        onPageError: (String, Boolean, String) -> Unit = { _, _, _ -> },
    ): AegisWebViewClient =
        AegisWebViewClient(
            broker = broker,
            sessionId = SESSION,
            tabId = TAB,
            onRendererGone = onRendererGone,
            requireNavigationConfirmation = requireConfirmation,
            onNavigationDenied = { code, _ -> deniedCodes.add(code) },
            onPageError = onPageError,
        )

    private fun stubAllow() {
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
        whenever(
            broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://example.com/", "navigation"),
        ).thenReturn(true)
    }

    private fun stubDeny(code: String = "url_policy") {
        whenever(
            broker.requestNavigationConfirmation(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
            ),
        ).thenReturn(Decision.Deny(DenyReason(code, "detail")))
    }

    // ------------------------------------------------------------- AD-008
    @Test
    fun navigateLoadsHttpsUrlWhenBrokerAllows() {
        stubAllow()
        val client = newClient()
        assertTrue(client.navigate(view, "https://example.com/"))
        verify(view).loadUrl("https://example.com/")
    }

    @Test
    fun navigateReturnsFalseWhenAuthorizationConsumptionFails() {
        stubAllow()
        whenever(broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(false)
        val client = newClient()
        assertFalse(client.navigate(view, "https://example.com/"))
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-009
    @Test
    fun topLevelDenialIsSurfacedToCaller() {
        stubDeny("url_policy")
        val client = newClient()
        assertFalse(client.navigate(view, "https://example.com/"))
        assertEquals(listOf("url_policy"), deniedCodes)
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-010
    @Test
    fun mainFrameHttpIsBlockedAndUpgraded() {
        // Allow 消费后 loadWhenAllowed=true → loadUrl 加载升级版 https
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/x", "navigation"))
            .thenReturn(Decision.Allow(allowAction.copy(origin = "https://example.com", canonicalParameters = "/x")))
        whenever(
            broker.consumeNavigation(
                allowAction.copy(origin = "https://example.com", canonicalParameters = "/x"),
                SESSION,
                TAB,
                0L,
                "https://example.com/x",
                "navigation",
            ),
        ).thenReturn(true)
        val client = newClient()
        val request = fakeRequest("http://example.com/x", isMainFrame = true)

        // 返回 true = WebView 原始 http 加载被阻断（升级由客户端经 broker 执行）
        assertTrue(client.shouldOverrideUrlLoading(view, request))
        // broker 收到的是升级后的 https URL（明文绝不透传决策层）
        verify(broker).requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/x", "navigation")
        verify(view).loadUrl("https://example.com/x")
    }

    // ------------------------------------------------------------- AD-011
    @Test
    fun subFrameHttpNeverHijacksTopLevel() {
        val client = newClient()
        // 子框架 Allow：消费成功但 loadWhenAllowed=false → 绝不 loadUrl 到顶层
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://ads.example/frame", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
        whenever(
            broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://ads.example/frame", "navigation"),
        ).thenReturn(true)
        val allowed =
            client.shouldOverrideUrlLoading(view, fakeRequest("http://ads.example/frame", isMainFrame = false))
        // Allow → return false（放行原始子框架加载——明文由 cleartext 禁用兜底）
        assertFalse(allowed)
        verify(view, never()).loadUrl(anyString())

        // 子框架 Deny：return true（阻断留痕）
        stubDeny("url_policy")
        val denied = client.shouldOverrideUrlLoading(view, fakeRequest("http://ads.example/frame", isMainFrame = false))
        assertTrue(denied)
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-012
    @Test
    fun renderProcessGoneReturnsTrueAndAdvancesGeneration() {
        var goneView: WebView? = null
        val client = newClient(onRendererGone = { goneView = it })
        val detail = mock(RenderProcessGoneDetail::class.java)
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(true)

        val handled = client.onRenderProcessGone(view, detail)

        // 官方 Termination Handling：必须返回 true（否则系统 kill Activity）
        assertTrue(handled)
        assertEquals(view, goneView)
        // 代际推进同步 broker（后续旧授权消费被代际门禁拒绝）
        verify(broker).updateDocumentGeneration(SESSION, TAB, 1L)
    }

    // ------------------------------------------------------------- AD-013
    @Test
    fun closeDestroysBrokerSession() {
        val client = newClient()
        client.close()
        verify(broker, times(1)).destroySession(SESSION)
    }

    // ------------------------------------------------------------- AD-014
    @Test
    fun uppercaseHttpSchemeIsUpgradedToHttps() {
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://Example.com/a", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
        whenever(
            broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://Example.com/a", "navigation"),
        ).thenReturn(true)
        val client = newClient()
        // T3 回归：HTTP:// 大写 scheme 必须升级（此前大小写敏感替换漏放明文）
        assertTrue(client.navigate(view, "HTTP://Example.com/a"))
        verify(view).loadUrl("https://Example.com/a")
    }

    // ------------------------------------------------------------- AD-015
    @Test
    fun approvePendingNavigationWithoutPendingIsDenied() {
        val client = newClient()
        assertFalse(client.approvePendingNavigation(view))
        assertFalse(client.rejectPendingNavigation())
        // 空边界：不触碰 broker（不得凭空创建/消费授权——更强于逐方法 never）
        org.mockito.Mockito.verifyNoInteractions(broker)
    }

    // ------------------------------------------------------------- 辅助

    /** WebResourceRequest 是接口——fake 实现免 mockito（url 走 mock Uri）。 */
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

    // ------------------------------------------------------------- AD-050
    @Test
    fun autoApproveBranchUsesInjectedDecisionSource() {
        val confirmationRequest =
            com.aegis.broker.ApprovalRequest(
                origin = "https://example.com",
                method = "GET",
                path = "/",
                scope = "navigation",
                expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("60s")),
                nonce = "pending-nonce",
            )
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(Decision.RequireConfirmation(confirmationRequest))
        whenever(broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(true)
        var injectedFor: com.aegis.broker.ApprovalRequest? = null
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                requireNavigationConfirmation = false,
                autoApproveDecision = { request, _, _ ->
                    injectedFor = request
                    Decision.Allow(allowAction)
                },
            )
        assertTrue(client.navigate(view, "https://example.com/"))
        // 决策来自注入源（收到的是核心登记的 request）且未硬编码触碰 broker 批准
        assertEquals(confirmationRequest, injectedFor)
        verify(broker, never()).approveNavigationConfirmation(confirmationRequest, "https://example.com/", "navigation")
        verify(view).loadUrl("https://example.com/")
    }

    @Test
    fun autoApproveBranchDeniedWhenInjectedDecisionDenies() {
        val confirmationRequest =
            com.aegis.broker.ApprovalRequest(
                origin = "https://example.com",
                method = "GET",
                path = "/",
                scope = "navigation",
                expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("60s")),
                nonce = "pending-nonce",
            )
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(Decision.RequireConfirmation(confirmationRequest))
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                requireNavigationConfirmation = false,
                autoApproveDecision = { _, _, _ -> Decision.Deny(DenyReason("url_policy", "detail")) },
            )
        assertFalse(client.navigate(view, "https://example.com/"))
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-053
    @Test
    fun onPageStartedAdvancesGenerationAndObservesUrl() {
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(true)
        var observed: String? = null
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                onPageUrlObserved = { observed = it },
            )
        client.onPageStarted(view, "https://example.com/", null)
        // 代际单步推进同步 broker（旧代授权在后续消费时被代际门禁拒绝）
        verify(broker).updateDocumentGeneration(SESSION, TAB, 1L)
        assertEquals("https://example.com/", observed)
        verify(view, never()).stopLoading()
    }

    @Test
    fun onPageStartedStopsLoadingWhenSessionIsStale() {
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(false)
        val client = newClient()
        client.onPageStarted(view, "https://example.com/", null)
        // 未注册/陈旧会话加载页面 → 立即停载（fail-closed）
        verify(view).stopLoading()
    }

    // ------------------------------------------------------------- AD-054
    @Test
    fun mainFrameHttpErrorIsReportedButSubFrameIsSilent() {
        val errors = mutableListOf<String>()
        val client = newClient(onPageError = { description, _, url -> errors.add("$description|$url") })
        val response = mock(WebResourceResponse::class.java)
        whenever(response.statusCode).thenReturn(500)

        // 子框架 5xx：不上报（不遮蔽整页内容）
        client.onReceivedHttpError(view, fakeRequest("https://ads.example/frame", isMainFrame = false), response)
        assertTrue(errors.isEmpty())

        // 主框架 5xx：上报错误面板
        client.onReceivedHttpError(view, fakeRequest("https://example.com/x", isMainFrame = true), response)
        assertEquals(listOf("服务器返回错误（HTTP 500）|https://example.com/x"), errors)
    }

    @Test
    fun httpErrorBelowThresholdIsNotReported() {
        val errors = mutableListOf<String>()
        val client = newClient(onPageError = { description, _, _ -> errors.add(description) })
        val response = mock(WebResourceResponse::class.java)
        whenever(response.statusCode).thenReturn(200)
        client.onReceivedHttpError(view, fakeRequest("https://example.com/x", isMainFrame = true), response)
        assertTrue(errors.isEmpty())
    }
}

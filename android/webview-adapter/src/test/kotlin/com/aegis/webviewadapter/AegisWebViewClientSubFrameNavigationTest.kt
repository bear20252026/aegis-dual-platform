package com.aegis.webviewadapter

import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebView
import com.aegis.broker.AndroidBroker
import com.aegis.broker.AuthorizedAction
import com.aegis.broker.Decision
import com.aegis.broker.DenyReason
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.mock
import org.mockito.Mockito.never
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import kotlin.time.Clock
import org.mockito.Mockito.`when` as whenever

/**
 * AegisWebViewClient 子框架导航判定 JVM 单测。
 *
 * detekt-修复（2026-10-02 审计云端实证）：自 AegisWebViewClientTest（829 行，
 * LargeClass 600 阈值）拆出子框架导航同域用例——AD-011/AD-246/AD-309
 * （升级重发）、AD-321（确认型 fail-closed）、AD-221（pending 期间子框架
 * 轻量路径不续期）。断言与桩原样搬移，不改语义。
 *
 * 前置（与原类同一 JVM 可测化口径）：
 * - android.util.Log 经 unitTests.returnDefaultValues 兜底；
 * - AndroidBroker/WebView/WebResourceRequest 经 mockito 5 inline mock。
 */
class AegisWebViewClientSubFrameNavigationTest {
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

    private fun newClient(requireConfirmation: Boolean = false): AegisWebViewClient =
        AegisWebViewClient(
            broker = broker,
            sessionId = SESSION,
            tabId = TAB,
            onRendererGone = {},
            requireNavigationConfirmation = requireConfirmation,
            onNavigationDenied = { code, _ -> deniedCodes.add(code) },
        )

    // ------------------------------------------------------------- AD-011 / AD-246 / AD-309
    @Test
    fun subFrameHttpIsBlockedAndResentUpgraded() {
        // AD-309（2026-10-02 审计）：子框架 Allow 与主框架同口径——升级只用于
        // 判定、放行仍载原始 http 的旧形态（cleartext 禁用下子框架静默失败）
        // 改为返回 true 阻断原始加载 + view.loadUrl(升级后 URL) 重发。
        val client = newClient()
        whenever(broker.evaluateNavigation(SESSION, TAB, 0L, "https://ads.example/frame", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
        val blocked =
            client.shouldOverrideUrlLoading(view, fakeRequest("http://ads.example/frame", isMainFrame = false))
        assertTrue("原始 http 子框架加载必须阻断", blocked)
        // broker 收到升级后 URL，且经 loadUrl 重发（不消费顶层授权对象）
        verify(broker).evaluateNavigation(SESSION, TAB, 0L, "https://ads.example/frame", "navigation")
        verify(view).loadUrl("https://ads.example/frame")
        verify(
            broker,
            never(),
        ).consumeNavigation(allowAction, SESSION, TAB, 0L, "https://ads.example/frame", "navigation")

        // 子框架 Deny：return true（阻断留痕，不重发）
        whenever(broker.evaluateNavigation(SESSION, TAB, 0L, "https://ads.example/frame", "navigation"))
            .thenReturn(
                Decision.Deny(
                    DenyReason("url_policy", "拒绝 URL: https://ads.example/frame?token=secret"),
                ),
            )
        val denied = client.shouldOverrideUrlLoading(view, fakeRequest("http://ads.example/frame", isMainFrame = false))
        assertTrue(denied)
        // Deny 后无第三次 loadUrl（上面 Allow 分支恰好一次）
        verify(view, times(1)).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-321
    @Test
    fun subFrameRequireConfirmationFailsClosed() {
        // 子框架 RequireConfirmation：无子框架确认 UI 面——fail-closed 阻断
        // （不弹确认、不放行、不登记 pending）
        val confirmationRequest = approvalRequest()
        whenever(broker.evaluateNavigation(SESSION, TAB, 0L, "https://ads.example/frame", "navigation"))
            .thenReturn(Decision.RequireConfirmation(confirmationRequest))
        var requested = false
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                requireNavigationConfirmation = true,
                onNavigationConfirmationRequested = { requested = true },
                onNavigationDenied = { code, _ -> deniedCodes.add(code) },
            )
        // detekt-修复（2026-10-02 审计云端实证）：MaxLineLength>120——链式调用折行
        val blocked =
            client.shouldOverrideUrlLoading(view, fakeRequest("https://ads.example/frame", isMainFrame = false))
        assertTrue("确认型子框架导航必须 fail-closed 阻断", blocked)
        assertFalse("不得登记确认请求（无子框架确认 UI 面）", requested)
        assertTrue(deniedCodes.isEmpty())
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-221
    @Test
    fun sessionRenewalIsSuppressedWhileConfirmationIsPending() {
        // 待审批确认期间不得续期——覆盖式重注册会孤儿化 Rust 核心的 pending
        // nonce（renewSessionBeforeDecision 门控的关键时序此前零测试）。
        // 注意：同一请求实例贯穿登记/批准（data class equals 含时间戳——
        // 每次新建实例会使 stub 匹配失效）
        val pendingRequest = approvalRequest()
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(Decision.RequireConfirmation(pendingRequest))
        val client = newClient(requireConfirmation = true)
        assertFalse(client.navigate(view, "https://example.com/"))
        verify(broker, times(1)).renewSession(SESSION, TAB)

        // pending 期间的子框架导航：轻量路径不续期（防孤儿化 pending nonce）
        whenever(broker.evaluateNavigation(SESSION, TAB, 0L, "https://ads.example/frame", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
        client.shouldOverrideUrlLoading(view, fakeRequest("https://ads.example/frame", isMainFrame = false))
        verify(broker, times(1)).renewSession(SESSION, TAB)

        // 批准消费后恢复续期
        whenever(broker.approveNavigationConfirmation(pendingRequest, "https://example.com/", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
        whenever(broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(true)
        assertTrue(client.approvePendingNavigation(view))
        client.navigate(view, "https://example.com/")
        verify(broker, times(2)).renewSession(SESSION, TAB)
    }

    // ------------------------------------------------------------- 辅助

    /** AD-216/AD-221：待审批请求构造器（多断言共用；data class equals 匹配 stub）。 */
    private fun approvalRequest(): com.aegis.broker.ApprovalRequest =
        com.aegis.broker.ApprovalRequest(
            origin = "https://example.com",
            method = "GET",
            path = "/",
            scope = "navigation",
            expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("60s")),
            nonce = "pending-nonce",
        )

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
}

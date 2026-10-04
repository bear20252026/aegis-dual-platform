package com.aegis.webviewadapter

import android.net.Uri
import android.net.http.SslError
import android.webkit.RenderProcessGoneDetail
import android.webkit.SafeBrowsingResponse
import android.webkit.SslErrorHandler
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import com.aegis.broker.AndroidBroker
import com.aegis.broker.AuthorizedAction
import com.aegis.broker.Decision
import com.aegis.broker.DenyReason
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.mockito.ArgumentCaptor
import org.mockito.ArgumentMatchers.anyLong
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.mock
import org.mockito.Mockito.never
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import kotlin.time.Clock
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
        onPageError: (String, String, Boolean, String) -> Unit = { _, _, _, _ -> },
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
        // 审计第六轮（2026-10-03）：兑换失败不得静默——顶层上抛可见拒绝提示
        // （此前只 return false，用户症状是「点了没反应」的死点击）
        assertEquals(listOf(WebViewErrorCodes.ERROR_NAVIGATION_NOT_CONSUMED), deniedCodes)
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
        // 审计第六轮（2026-10-03）：回调内放行加载改经 view.post 投递
        runPostedLoad()
        verify(view).loadUrl("https://example.com/x")
    }

    // detekt-修复（2026-10-02 审计云端实证）：子框架导航域（AD-011/AD-246/AD-309、
    // AD-321、AD-221 子框架续期抑制）拆至 AegisWebViewClientSubFrameNavigationTest
    // （原类 829 行触发 LargeClass(600)）——断言原样搬移。

    // ------------------------------------------------------------- AD-321
    @Test
    fun onReceivedErrorMainFrameReportsAndSubFrameStaysSilent() {
        // onReceivedError：主框架加载失败上报错误面板；子框架静默（不遮蔽整页）
        val errors = mutableListOf<String>()
        val client = newClient(onPageError = { code, detail, _, url -> errors.add("$code:$detail|$url") })
        val error = mock(android.webkit.WebResourceError::class.java)
        whenever(error.errorCode).thenReturn(-2)
        whenever(error.description).thenReturn("host lookup")

        // 子框架：静默
        client.onReceivedError(view, fakeRequest("https://ads.example/frame", isMainFrame = false), error)
        assertTrue(errors.isEmpty())

        // 主框架：上报（错误码结构——文案映射在 app 层）
        client.onReceivedError(view, fakeRequest("https://example.com/x", isMainFrame = true), error)
        assertEquals(listOf("${WebViewErrorCodes.ERROR_MAIN_FRAME}:-2:host lookup|https://example.com/x"), errors)
    }

    // ------------------------------------------------------------- AD-216
    @Test
    fun pendingConfirmationIsNotSurfacedAsDenial() {
        // 「待确认」与「被拒」共用 false 返回——确认挂起路径只弹确认对话框，
        // 不得触发 onNavigationDenied（app 层据 pending 非空抑制错误提示）
        val confirmationRequest = approvalRequest()
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
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
        assertFalse(client.navigate(view, "https://example.com/"))
        assertTrue("确认请求必须上抛 UI", requested)
        assertTrue("pending 不得触发 onNavigationDenied", deniedCodes.isEmpty())
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-221
    // detekt-修复（2026-10-02 审计云端实证）：sessionRenewalIsSuppressed...（含
    // pending 期间子框架续期抑制断言）已随子框架域迁至
    // AegisWebViewClientSubFrameNavigationTest。

    // ------------------------------------------------------------- AD-211
    @Test
    fun denialLogLineRedactsUrlsEmbeddedInDetailAndUrl() {
        // detail 内嵌完整明文 URL（AndroidBroker deny("url_policy", "拒绝 URL: $rawUrl")
        // 直接拼原文）——日志面必须一并脱敏（query 中 token/搜索词不入 logcat）
        val reason = DenyReason("url_policy", "拒绝 URL: https://evil.com/dl?token=secret&q=1")
        val line = WebViewErrorCodes.denialLogLine(reason, "https://evil.com/dl?token=secret")
        assertFalse("日志行不得含明文 query", line.contains("token=secret"))
        assertFalse(line.contains("q=1"))
        assertTrue(line.contains("code=url_policy"))
        assertTrue("脱敏后保留 scheme+host+path", line.contains("https://evil.com/dl…"))
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

    /**
     * 审计第六轮（2026-10-03）：回调内放行加载经 view.post 投递——mock WebView
     * 的 post 不会执行 Runnable，测试取出投递任务手动运行（等价主线程下一轮），
     * 以此断言「投递的就是这一条加载」而非放任同步调用。
     */
    private fun runPostedLoad() {
        val captor = ArgumentCaptor.forClass(Runnable::class.java)
        verify(view).post(captor.capture())
        captor.value.run()
    }

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
                onNavigationDenied = { code, _ -> deniedCodes.add(code) },
                autoApproveDecision = { _, _, _ -> Decision.Deny(DenyReason("url_policy", "detail")) },
            )
        assertFalse(client.navigate(view, "https://example.com/"))
        verify(view, never()).loadUrl(anyString())
        // 审计第六轮（2026-10-03）：自动批准决策本身被拒 → 上抛的是注入的
        // reason code（策略口径），不得谎报为 navigation_not_consumed 兑换失败
        assertEquals(listOf("url_policy"), deniedCodes)
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
        val client = newClient(onPageError = { code, detail, _, url -> errors.add("$code:$detail|$url") })
        val response = mock(WebResourceResponse::class.java)
        whenever(response.statusCode).thenReturn(500)

        // 子框架 5xx：不上报（不遮蔽整页内容）
        client.onReceivedHttpError(view, fakeRequest("https://ads.example/frame", isMainFrame = false), response)
        assertTrue(errors.isEmpty())

        // 主框架 5xx：上报错误面板（AD-035：错误码结构，文案映射在 app 层）
        client.onReceivedHttpError(view, fakeRequest("https://example.com/x", isMainFrame = true), response)
        assertEquals(listOf("http_error:500|https://example.com/x"), errors)
    }

    @Test
    fun httpErrorBelowThresholdIsNotReported() {
        val errors = mutableListOf<String>()
        val client = newClient(onPageError = { code, _, _, _ -> errors.add(code) })
        val response = mock(WebResourceResponse::class.java)
        whenever(response.statusCode).thenReturn(200)
        client.onReceivedHttpError(view, fakeRequest("https://example.com/x", isMainFrame = true), response)
        assertTrue(errors.isEmpty())
    }

    // ------------------------------------------------------------- AD-177
    @Test
    fun newTopNavigationWhilePendingRejectsOldNonce() {
        // 待审批确认框打开期间的新顶层导航：必须先显式撤销旧 nonce（核心侧
        // 的 pending 不得孤儿化），再对新 URL 重新走确认流程——旧实现直接
        // return false（新导航被静默吞掉）。锁定「撤销旧 → 登记新」两步。
        val oldRequest = approvalRequest()
        val newRequest =
            com.aegis.broker.ApprovalRequest(
                origin = "https://other.example",
                method = "GET",
                path = "/new",
                scope = "navigation",
                expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("60s")),
                nonce = "new-nonce",
            )
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(Decision.RequireConfirmation(oldRequest))
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://other.example/new", "navigation"))
            .thenReturn(Decision.RequireConfirmation(newRequest))
        val requestedOrigins = mutableListOf<String>()
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                requireNavigationConfirmation = true,
                onNavigationConfirmationRequested = { requestedOrigins.add(it.origin) },
                onNavigationDenied = { code, _ -> deniedCodes.add(code) },
            )
        // 第一次导航：登记 pending #1
        assertFalse(client.navigate(view, "https://example.com/"))
        // 第二次导航：旧 nonce 被显式撤销 + 新请求登记
        assertFalse(client.navigate(view, "https://other.example/new"))
        verify(broker, times(1)).rejectNavigationConfirmation(oldRequest)
        assertEquals(listOf("https://example.com", "https://other.example"), requestedOrigins)
        // 旧请求被撤销后不得再被批准兑换
        verify(broker, never()).approveNavigationConfirmation(oldRequest, "https://example.com/", "navigation")
    }

    // ------------------------------------------------------------- AD-201
    @Test
    fun generationAdvanceFailureRollsBackLocalCounter() {
        // 核心拒绝代际推进（未注册/陈旧会话）时本地自增必须回滚——否则本地
        // 代际与核心永久分叉，此后每次单步推进都被拒。锁定：两次页面启动
        // 各自都以「同一目标代际」尝试（本地从未超前）。
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(false)
        val client = newClient()
        client.onPageStarted(view, "https://example.com/first", null)
        client.onPageStarted(view, "https://example.com/second", null)
        // 两次尝试都是 +1（第二次若未回滚会尝试 +2 并被单步门禁拒绝）
        verify(broker, times(2)).updateDocumentGeneration(SESSION, TAB, 1L)
    }

    @Test
    fun renderProcessGoneFailureAlsoRollsBackLocalCounter() {
        val client = newClient(onRendererGone = {})
        val detail = mock(RenderProcessGoneDetail::class.java)
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(false)
        assertTrue(client.onRenderProcessGone(view, detail))
        // 回滚后重复的崩溃路径仍以 +1 重试（不得分叉）
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(true)
        assertTrue(client.onRenderProcessGone(view, detail))
        verify(broker, times(2)).updateDocumentGeneration(SESSION, TAB, 1L)
    }

    // ------------------------------------------------------------- AD-255
    // 主框架判定以 isForMainFrame 为主分支——https 主框架链接不再漏进子框架
    // 轻量分支（确认对话框永不出现、Deny 不上抛的静默死链）。

    @Test
    fun mainFrameHttpsConfirmationIsSurfacedNotSilentlyBlocked() {
        val confirmationRequest = approvalRequest()
        whenever(broker.requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation"))
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
        // 返回 true = 阻断 WebView 原始加载（由客户端经批准流程恢复）
        assertTrue(client.shouldOverrideUrlLoading(view, fakeRequest("https://example.com/", isMainFrame = true)))
        assertTrue("主框架 RequireConfirmation 必须走确认登记（不再静默阻断）", requested)
        assertTrue(deniedCodes.isEmpty())
        verify(view, never()).loadUrl(anyString())
    }

    @Test
    fun mainFrameHttpsDenialIsSurfacedTopLevel() {
        stubDeny("url_policy")
        val client = newClient()
        val blocked = client.shouldOverrideUrlLoading(view, fakeRequest("https://evil.example/", isMainFrame = true))
        // 返回 true 阻断 + onNavigationDenied 顶层上抛（原实现落子框架分支
        // 只留日志——静默死链）
        assertTrue(blocked)
        assertEquals(listOf("url_policy"), deniedCodes)
        verify(view, never()).loadUrl(anyString())
    }

    @Test
    fun mainFrameHttpsAllowLoadsThroughFullChain() {
        stubAllow()
        val client = newClient()
        assertTrue(client.shouldOverrideUrlLoading(view, fakeRequest("https://example.com/", isMainFrame = true)))
        // 全链（requestNavigationConfirmation + consumeNavigation + loadUrl）
        verify(broker).requestNavigationConfirmation(SESSION, TAB, 0L, "https://example.com/", "navigation")
        verify(broker).consumeNavigation(allowAction, SESSION, TAB, 0L, "https://example.com/", "navigation")
        // 审计第六轮（2026-10-03）：回调内加载改投递（shouldOverrideUrlLoading
        // 契约不得同步改动 WebView 状态）——取出投递任务执行后照常加载
        runPostedLoad()
        verify(view).loadUrl("https://example.com/")
    }

    @Test
    fun mainFrameConsumeFailureFromCallbackIsSurfacedNotSilentDeadClick() {
        // 审计第六轮（2026-10-03）：真机症状复现——标签闲置过 120s TTL 后点
        // 任意链接，consumeNavigation 拒绝兑换（会话过期/代际不符/nonce 重放/
        // Kotlin expiresAt 已到），旧实现「什么都不加载、什么都不提示」。
        // 现经 denied(topLevel = true) 上抛 navigation_not_consumed。
        stubAllow()
        whenever(broker.consumeNavigation(allowAction, SESSION, TAB, 0L, "https://example.com/", "navigation"))
            .thenReturn(false)
        val client = newClient()
        val blocked = client.shouldOverrideUrlLoading(view, fakeRequest("https://example.com/", isMainFrame = true))
        assertTrue("已接管该导航（返回 true 阻断 WebView 原始加载）", blocked)
        assertEquals(listOf(WebViewErrorCodes.ERROR_NAVIGATION_NOT_CONSUMED), deniedCodes)
        verify(view, never()).loadUrl(anyString())
    }

    @Test
    fun postedLoadAfterCloseNeverTouchesDestroyedWebView() {
        // 审计第六轮（2026-10-03）：投递任务与 tearDown→release→close 竞态——
        // AD-281 后销毁序列不再 loadUrl(about:blank) 占位，排队中的放行加载
        // 必须由 closed 标志短路（绝不对已 destroy 的 WebView 触达 loadUrl）。
        stubAllow()
        val client = newClient()
        assertTrue(client.shouldOverrideUrlLoading(view, fakeRequest("https://example.com/", isMainFrame = true)))
        val captor = ArgumentCaptor.forClass(Runnable::class.java)
        verify(view).post(captor.capture())
        client.close()
        captor.value.run()
        verify(view, never()).loadUrl(anyString())
    }

    // ------------------------------------------------------------- AD-284
    @Test
    fun mailtoMainFrameNavigationSurfacesUnsupportedSchemeFeedback() {
        var unsupported: String? = null
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                onUnsupportedSchemeNavigation = { scheme, _ -> unsupported = scheme },
            )
        val blocked = client.shouldOverrideUrlLoading(view, fakeRequest("mailto:a@b.example", isMainFrame = true))
        assertTrue("外跳 scheme 必须阻断 WebView 原始加载", blocked)
        assertEquals("mailto", unsupported)
        // 不与恶意 scheme 同走 Deny 提示（onNavigationDenied 不触发）
        assertTrue(deniedCodes.isEmpty())
        verify(
            broker,
            never(),
        ).requestNavigationConfirmation(anyString(), anyString(), anyLong(), anyString(), anyString())

        // tel: 同口径
        val telBlocked = client.shouldOverrideUrlLoading(view, fakeRequest("tel:10086", isMainFrame = true))
        assertTrue(telBlocked)
        assertEquals("tel", unsupported)
    }

    // ------------------------------------------------------------- AD-304
    @Test
    fun newExternalHandlerSchemesSurfaceUnsupportedSchemeFeedback() {
        // AD-304（2026-10-02 审计）：smsto/mmsto/geo 与 mailto/tel/sms 同为
        // 系统分发形态——主框架导航必须走「不支持该类链接」分型上抛，
        // 不得落策略拒绝（onNavigationDenied/恐吓提示）或静默放行。
        assertTrue(
            "externalHandlerSchemes 缺少 smsto（AD-304）",
            "smsto" in AegisWebViewClient.externalHandlerSchemes,
        )
        assertTrue(
            "externalHandlerSchemes 缺少 mmsto（AD-304）",
            "mmsto" in AegisWebViewClient.externalHandlerSchemes,
        )
        assertTrue(
            "externalHandlerSchemes 缺少 geo（AD-304）",
            "geo" in AegisWebViewClient.externalHandlerSchemes,
        )
        val observed = mutableListOf<String>()
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                onUnsupportedSchemeNavigation = { scheme, _ -> observed.add(scheme) },
            )
        listOf("smsto:10086", "mmsto:10086", "geo:39.9,116.4").forEach { url ->
            val blocked = client.shouldOverrideUrlLoading(view, fakeRequest(url, isMainFrame = true))
            assertTrue("外跳 scheme $url 必须阻断 WebView 原始加载", blocked)
            // 不与恶意 scheme 同走 Deny 提示
            assertTrue(deniedCodes.isEmpty())
        }
        assertEquals(listOf("smsto", "mmsto", "geo"), observed)
        verify(
            broker,
            never(),
        ).requestNavigationConfirmation(anyString(), anyString(), anyLong(), anyString(), anyString())
    }

    // ------------------------------------------------------------- AD-256
    @Test
    fun onPageStartedRecheckStopsPolicyDeniedRedirect() {
        // 302 重定向不经 shouldOverrideUrlLoading——onPageStarted 复核 Deny 即
        // stopLoading + 顶层上抛，且阻断 URL 不进地址栏
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(true)
        whenever(broker.evaluateNavigation(SESSION, TAB, 1L, "https://evil.example/redirected", "navigation"))
            .thenReturn(Decision.Deny(DenyReason("url_policy", "拒绝 URL: https://evil.example/redirected?token=1")))
        var observed: String? = "sentinel"
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                onNavigationDenied = { code, _ -> deniedCodes.add(code) },
                onPageUrlObserved = { observed = it },
            )
        client.onPageStarted(view, "https://evil.example/redirected", null)
        verify(view).stopLoading()
        assertEquals(listOf("url_policy"), deniedCodes)
        assertEquals("阻断的 URL 不得上抛地址栏", "sentinel", observed)
    }

    @Test
    fun onPageStartedRecheckAllowsLegitimateLoadAndObservesUrl() {
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(true)
        whenever(broker.evaluateNavigation(SESSION, TAB, 1L, "https://example.com/", "navigation"))
            .thenReturn(Decision.Allow(allowAction))
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
        verify(view, never()).stopLoading()
        assertEquals("https://example.com/", observed)
    }

    @Test
    fun onPageStartedSkipsRecheckForNonHttpSchemes() {
        // 受信首页（file://）/about: 页不做策略复核（否则首页加载被误杀）
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
        client.onPageStarted(view, "file:///android_asset/start.html", null)
        verify(broker, never()).evaluateNavigation(anyString(), anyString(), anyLong(), anyString(), anyString())
        verify(view, never()).stopLoading()
        assertEquals("file:///android_asset/start.html", observed)
    }

    // ------------------------------------------------------------- AD-265
    @Test
    fun onPageStartedStaleSessionDoesNotObserveBlockedUrl() {
        // 代际推进失败已 stopLoading——阻断 URL 不得再上抛地址栏（状态污染）
        whenever(broker.updateDocumentGeneration(SESSION, TAB, 1L)).thenReturn(false)
        var observed: String? = "sentinel"
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = SESSION,
                tabId = TAB,
                onRendererGone = {},
                onPageUrlObserved = { observed = it },
            )
        client.onPageStarted(view, "https://stale.example/blocked", null)
        verify(view).stopLoading()
        assertEquals("阻断的 URL 不得上抛地址栏（AD-265）", "sentinel", observed)
    }

    // ------------------------------------------------------------- AD-271/AD-273
    @Test
    fun sslErrorOnMainFrameCancelsAndReportsErrorPanel() {
        val errors = mutableListOf<String>()
        val client = newClient(onPageError = { code, _, _, _ -> errors.add(code) })
        val handler = mock(SslErrorHandler::class.java)
        val error = mock(SslError::class.java)
        whenever(error.url).thenReturn("https://example.com/")
        whenever(error.primaryError).thenReturn(3)
        whenever(view.url).thenReturn("https://example.com/")

        client.onReceivedSslError(view, handler, error)

        // 绝不 proceed；主框架归属 → 错误面板上抛
        verify(handler).cancel()
        verify(handler, never()).proceed()
        assertEquals(listOf(WebViewErrorCodes.ERROR_SSL_CERTIFICATE), errors)
    }

    @Test
    fun sslErrorOnSubResourceCancelsWithoutMaskingWholePage() {
        // 归属判定：error.url 与主框架 URL 不一致（子资源形态）→ 只 cancel
        // + 留痕，不上抛整页遮罩
        val errors = mutableListOf<String>()
        val client = newClient(onPageError = { code, _, _, _ -> errors.add(code) })
        val handler = mock(SslErrorHandler::class.java)
        val error = mock(SslError::class.java)
        whenever(error.url).thenReturn("https://cdn.example/sub.js")
        whenever(error.primaryError).thenReturn(2)
        whenever(view.url).thenReturn("https://example.com/")

        client.onReceivedSslError(view, handler, error)

        verify(handler).cancel()
        verify(handler, never()).proceed()
        assertTrue("子资源证书错不得遮蔽整页", errors.isEmpty())
    }

    // ------------------------------------------------------------- AD-273/AD-291
    @Test
    fun safeBrowsingHitNeverProceedsAndFallsBackWithoutHistory() {
        // 阻断语义锁定：绝不 proceed；有历史 backToSafety。无历史的插页
        // 分支依赖 Build.VERSION.SDK_INT ≥ 27（JVM 桩下为 0 → 走 backToSafety
        // 兜底，插页分支由真机/Robolectric 覆盖）。
        val response = mock(SafeBrowsingResponse::class.java)
        val client = newClient()
        whenever(view.canGoBack()).thenReturn(true)
        client.onSafeBrowsingHit(view, fakeRequest("https://evil.example/x", isMainFrame = true), 5, response)
        verify(response).backToSafety(true)
        verify(response, never()).proceed(org.mockito.ArgumentMatchers.anyBoolean())

        // 无历史 + JVM 桩 SDK_INT=0 → 仍 backToSafety（不 proceed、不崩溃）
        val response2 = mock(SafeBrowsingResponse::class.java)
        val view2 = mock(WebView::class.java)
        whenever(view2.canGoBack()).thenReturn(false)
        client.onSafeBrowsingHit(view2, fakeRequest("https://evil.example/y", isMainFrame = true), 5, response2)
        verify(response2).backToSafety(true)
        verify(response2, never()).proceed(org.mockito.ArgumentMatchers.anyBoolean())
        verify(response2, never()).showInterstitial(org.mockito.ArgumentMatchers.anyBoolean())
    }
}

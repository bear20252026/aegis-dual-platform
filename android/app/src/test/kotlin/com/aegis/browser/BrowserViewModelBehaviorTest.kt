package com.aegis.browser

import android.app.Application
import android.webkit.WebView
import androidx.test.core.app.ApplicationProvider
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
import com.aegis.broker.AuthorizedAction
import com.aegis.broker.Decision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mockito.mock
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import kotlin.time.Clock
import org.mockito.Mockito.`when` as whenever

/**
 * BrowserViewModel 行为 JVM 单测（Robolectric——真实 WebView 创建链）。
 *
 * AD-152（布局枚举）/ AD-158（跨标签批准拒绝）/ AD-159（切换撤销待审批）/
 * AD-160（refresh 草稿保护）——审计 2026-09-23 清单·A7 批：这四条此前
 * 「无测试」，且 A6 批拆分后 ViewModel 行为面无任何直接回归。
 *
 * 桩口径：AndroidBroker 经 mockito 5 inline mock（final 类），registerSession
 * 放行（WebView 创建链的 fail-closed 注册必须成功）；其余 broker 交互由
 * webview-adapter/broker 各自的测试面覆盖。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class BrowserViewModelBehaviorTest {
    private lateinit var broker: AndroidBroker
    private lateinit var viewModel: BrowserViewModel

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
        viewModel = BrowserViewModel(broker)
        val application = ApplicationProvider.getApplicationContext<Application>()
        viewModel.init(application)
    }

    private fun approvalRequest(): ApprovalRequest =
        ApprovalRequest(
            origin = "https://example.com",
            method = "GET",
            path = "/",
            scope = "navigation",
            expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("60s")),
            nonce = "behavior-test-nonce",
        )

    // ------------------------------------------------------------- AD-152

    @Test
    fun tabsPositionDefaultsToTopAndTogglesToLeftAndBack() {
        assertEquals(TabsPosition.TOP, viewModel.tabsPosition.value)
        viewModel.toggleTabsPosition()
        assertEquals(TabsPosition.LEFT, viewModel.tabsPosition.value)
        viewModel.toggleTabsPosition()
        assertEquals(TabsPosition.TOP, viewModel.tabsPosition.value)
    }

    // ------------------------------------------------------------- AD-158

    @Test
    fun approvalFromAnotherTabIsRejectedWithSwitchBackAlert() {
        // init 后必有当前标签（后续断言的锚点）
        assertNotNull(viewModel.currentWebViewOrNull())
        // 待审批挂起绑定到一个「非当前标签」的 WebView（跨标签场景）
        viewModel.registerPendingConfirmation(mock(WebView::class.java), approvalRequest())

        val approved = viewModel.approvePendingNavigationConfirmation()

        assertFalse("跨标签批准必须拒绝（不得在错误 WebView 上消费授权）", approved)
        assertEquals(
            "拒绝必须上抛「切回原标签」提示（不再静默）",
            ApplicationProvider.getApplicationContext<Application>().getString(R.string.confirm_switch_back),
            viewModel.webViewAlert.value?.message,
        )
        // 拒绝路径不清除 pending（用户切回原标签后仍可正常批准）
        assertTrue(viewModel.pendingNavigationConfirmation.value != null)
    }

    @Test
    fun approvalWithoutPendingIsDenied() {
        assertFalse(viewModel.approvePendingNavigationConfirmation())
    }

    // ------------------------------------------------------------- AD-159

    @Test
    fun switchingTabsRejectsPendingConfirmation() {
        // tab0（当前）：登记待审批 → 新建标签（切走）→ pending 必须撤销
        val tab0WebView = viewModel.currentWebViewOrNull() ?: error("init 后必有当前标签")
        viewModel.registerPendingConfirmation(tab0WebView, approvalRequest())
        assertTrue(viewModel.pendingNavigationConfirmation.value != null)

        viewModel.newTab(ApplicationProvider.getApplicationContext())

        assertNull("切换（新建即切换）必须撤销待审批——待确认 nonce 不得跨标签存续", viewModel.pendingNavigationConfirmation.value)
    }

    @Test
    fun switchingBackToPendingTabRequiresFreshConfirmation() {
        viewModel.newTab(ApplicationProvider.getApplicationContext())
        val tab1WebView = viewModel.currentWebViewOrNull() ?: error("新建后必有当前标签")
        viewModel.registerPendingConfirmation(tab1WebView, approvalRequest())

        viewModel.switchTo(0)

        assertNull("switchTo 路径同样必须撤销待审批", viewModel.pendingNavigationConfirmation.value)
    }

    // ------------------------------------------------------------- AD-160

    @Test
    fun refreshDoesNotOverwriteUncommittedAddressDraft() {
        val draft = "user is typing a query"
        viewModel.updateAddress(draft)
        assertEquals(draft, viewModel.address.value)

        // refresh（页面事件/标签切换触发的状态同步）不得覆盖未提交草稿
        viewModel.refresh()
        assertEquals("草稿保护失效——后台同步覆盖了用户输入", draft, viewModel.address.value)
    }

    @Test
    fun switchingTabClearsDraftAndShowsTargetTabAddress() {
        val draft = "half typed url"
        viewModel.updateAddress(draft)
        viewModel.newTab(ApplicationProvider.getApplicationContext())

        // 新标签 URL 为受信首页 → 地址栏显示首页占位（AD-063）而非草稿
        assertEquals(BrowserViewModel.HOME_DISPLAY_URL, viewModel.address.value)
        assertNotEquals(draft, viewModel.address.value)
    }

    // ------------------------------------------------------------- 防御边界

    @Test
    fun indexOfBoundsSwitchIsIgnored() {
        val before = viewModel.activeIndex.value
        viewModel.switchTo(99)
        assertEquals("越界切换必须静默忽略（对齐类内索引操作约定）", before, viewModel.activeIndex.value)
    }

    @Test
    fun closeLastTabIsRefused() {
        // setUp 后仅剩一个标签（浏览器约定）：最后一个不可关
        val sizeBefore = viewModel.getTabManager()?.size ?: error("tabManager 必须已初始化")
        viewModel.closeTab(0)
        assertEquals("最后一个标签必须保留", sizeBefore, viewModel.getTabManager()?.size)
    }

    // ---------------- AD-303（2026-10-02 审计）：地址栏外跳 scheme 分型 ----------------

    @Test
    fun addressBarExternalSchemeShowsUnsupportedToastNotRejectionAlert() {
        // tel: 输入：走「不支持该类链接」瞬时 Toast（与 WebView 内链接点击
        // 同款反馈），不再弹「无法通过安全策略验证」恐吓对话框
        viewModel.updateAddress("tel:10086")
        viewModel.navigateToAddress()
        assertNull("外跳 scheme 不得弹策略拒绝提示", viewModel.webViewAlert.value)
        val app = ApplicationProvider.getApplicationContext<Application>()
        assertEquals(
            app.getString(R.string.unsupported_link_scheme),
            org.robolectric.shadows.ShadowToast.textOfLatestToast,
        )
    }

    @Test
    fun addressBarForbiddenSchemeKeepsRejectionAlert() {
        // 非外跳的非法 scheme（javascript:）保持既有拒绝提示（fail-closed）
        viewModel.updateAddress("javascript:alert(1)")
        viewModel.navigateToAddress()
        val app = ApplicationProvider.getApplicationContext<Application>()
        assertEquals(
            app.getString(R.string.nav_rejected),
            viewModel.webViewAlert.value?.message,
        )
    }

    // ---------------- AD-328（2026-10-02 审计）：外链不覆写地址草稿 ----------------

    @Test
    fun openExternalUrlDoesNotOverwriteActiveAddressDraft() {
        stubBrokerAllowChain()
        viewModel.updateAddress("draft in progress")
        viewModel.openExternalUrl("https://external.example/x")
        assertEquals("外链 intent 不得覆写未提交草稿", "draft in progress", viewModel.address.value)
    }

    @Test
    fun openExternalUrlOverwritesAddressWhenNoDraftActive() {
        stubBrokerAllowChain()
        viewModel.openExternalUrl("https://external.example/x")
        assertEquals("https://external.example/x", viewModel.address.value)
    }

    // ---------------- AD-326（2026-10-02 审计）：标签会话持久化 ----------------

    @Test
    fun sessionStateRestoreRebuildsTabsFromSavedHttpsUrls() {
        val bundle =
            android.os.Bundle().apply {
                putStringArrayList(
                    BrowserViewModel.STATE_TAB_URLS,
                    arrayListOf("https://a.example/", "https://b.example/"),
                )
                putInt(BrowserViewModel.STATE_ACTIVE_TAB_INDEX, 1)
            }
        val restored = BrowserViewModel(broker)
        restored.init(ApplicationProvider.getApplicationContext(), bundle)
        assertEquals("恢复标签数", 2, restored.tabs.value.size)
        assertEquals("https://a.example/", restored.tabs.value[0].url)
        assertEquals("https://b.example/", restored.tabs.value[1].url)
        assertEquals("激活位恢复", 1, restored.activeIndex.value)
    }

    @Test
    fun sessionStateRestoreIgnoresNonHttpsEntries() {
        // 恢复侧防御：非 https 条目（file:/about:/http 明文）不参与重建
        val bundle =
            android.os.Bundle().apply {
                putStringArrayList(
                    BrowserViewModel.STATE_TAB_URLS,
                    arrayListOf("http://plain.example/", "file:///android_asset/start.html"),
                )
            }
        val restored = BrowserViewModel(broker)
        restored.init(ApplicationProvider.getApplicationContext(), bundle)
        assertEquals("非 https 全滤除后回落单标签冷启动", 1, restored.tabs.value.size)
    }

    @Test
    fun writeSessionStatePersistsOnlyHttpsUrlsAndActiveIndex() {
        val tm = viewModel.getTabManager() ?: error("tabManager 必须已初始化")
        // 首页标签 url 为 file://（不外存）；更新为 https 后外存
        tm.current()?.let { tm.updateUrl(it.id, "https://keep.example/page") }
        val bundle = android.os.Bundle()
        viewModel.writeSessionState(bundle)
        assertEquals(
            arrayListOf("https://keep.example/page"),
            bundle.getStringArrayList(BrowserViewModel.STATE_TAB_URLS),
        )
        assertEquals(0, bundle.getInt(BrowserViewModel.STATE_ACTIVE_TAB_INDEX))
    }

    @Test
    fun writeSessionStateFiltersOutFileHomeUrl() {
        val bundle = android.os.Bundle()
        viewModel.writeSessionState(bundle)
        assertEquals(
            "file:// 首页不外存（恢复由 openTrustedHome 承担）",
            arrayListOf<String>(),
            bundle.getStringArrayList(BrowserViewModel.STATE_TAB_URLS),
        )
    }

    // ---------------- AD-327（2026-10-02 审计）：三入口行为 ----------------

    @Test
    fun retryCurrentPageClearsErrorPanel() {
        val wv = viewModel.currentWebViewOrNull() ?: error("init 后必有当前标签")
        raiseMainFrameSslError(wv)
        org.junit.Assert.assertNotNull("前置：错误面板已上抛", viewModel.pageError.value)
        viewModel.retryCurrentPage()
        assertNull("重试入口必须清除错误面板", viewModel.pageError.value)
    }

    @Test
    fun returnToSafeHomeLoadsTrustedHomeUrl() {
        raiseMainFrameSslError(viewModel.currentWebViewOrNull() ?: error("init 后必有当前标签"))
        viewModel.returnToSafeHome()
        val wv = viewModel.currentWebViewOrNull() ?: error("init 后必有当前标签")
        assertEquals(BrowserViewModel.HOME_URL, shadowOf(wv).lastLoadedUrl)
        assertNull("返回安全页清除错误面板", viewModel.pageError.value)
    }

    @Test
    fun openExternalUrlNavigatesThroughSecureChain() {
        stubBrokerAllowChain()
        viewModel.openExternalUrl("https://chain.example/path")
        val wv = viewModel.currentWebViewOrNull() ?: error("init 后必有当前标签")
        assertEquals("经归一 + broker 授权后 loadUrl", "https://chain.example/path", shadowOf(wv).lastLoadedUrl)
    }

    // ---------------- 辅助（AD-326/327/328 共用） ----------------

    /** 全链放行桩：requestNavigationConfirmation→Allow + consumeNavigation→true。 */
    private fun stubBrokerAllowChain() {
        val action =
            AuthorizedAction(
                sessionId = "stub-session",
                tabId = "stub-tab",
                documentGeneration = 0,
                origin = "https://stub.example",
                method = "GET",
                canonicalParameters = "/",
                scope = "navigation",
                expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("120s")),
                nonce = "stub-nonce",
                policyVersion = "1.0",
            )
        whenever(
            broker.requestNavigationConfirmation(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
            ),
        ).thenReturn(Decision.Allow(action))
        whenever(
            broker.consumeNavigation(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
            ),
        ).thenReturn(true)
    }

    /** 主框架 SSL 错误注入：驱动 AegisWebViewClient.onReceivedSslError 上抛面板。 */
    private fun raiseMainFrameSslError(wv: WebView) {
        val handler = mock(android.net.http.SslErrorHandler::class.java)
        val error = mock(android.net.http.SslError::class.java)
        whenever(error.url).thenReturn("https://example.com/")
        whenever(error.primaryError).thenReturn(3)
        wv.loadUrl("https://example.com/") // view.url 与 error.url 归属一致（主框架）
        wv.webViewClient.onReceivedSslError(wv, handler, error)
    }
}

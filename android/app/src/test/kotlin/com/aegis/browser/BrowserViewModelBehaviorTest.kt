package com.aegis.browser

import android.app.Application
import android.webkit.WebView
import androidx.test.core.app.ApplicationProvider
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
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
            viewModel.webViewAlert.value,
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
}

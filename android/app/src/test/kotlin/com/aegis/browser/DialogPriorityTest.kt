package com.aegis.browser

import android.webkit.WebView
import com.aegis.broker.ApprovalRequest
import kotlinx.datetime.Clock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.mockito.Mockito.mock

/**
 * AD-151（审计 2026-09-23 清单·A7 批）：对话框单槽状态机优先级锁定——
 * 三对话框（待审批导航确认 / WebView 安全提示 / 阅读模式）同刻非空时
 * 只允许呈现安全优先级最高者；全空时无对话框。任何一处优先级倒置
 * （如提示遮蔽审批框——误 dismiss 即导航阻断）在此失败。
 */
class DialogPriorityTest {
    private fun pending(): PendingNavigationConfirmation =
        PendingNavigationConfirmation(
            webView = mock(WebView::class.java),
            request =
                ApprovalRequest(
                    origin = "https://example.com",
                    method = "GET",
                    path = "/",
                    scope = "navigation",
                    expiresAt = Clock.System.now().plus(kotlin.time.Duration.parse("60s")),
                    nonce = "nonce",
                ),
        )

    @Test
    fun emptyStateYieldsNoDialog() {
        assertNull(resolveActiveDialog(null, null, null))
    }

    @Test
    fun singleStatesResolveToTheirOwnSlot() {
        assertEquals(ActiveDialog.PENDING_CONFIRMATION, resolveActiveDialog(pending(), null, null))
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, "提示", null))
        assertEquals(
            ActiveDialog.READER_CONTENT,
            resolveActiveDialog(null, null, ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun pendingConfirmationBeatsAlertAndReader() {
        assertEquals(
            ActiveDialog.PENDING_CONFIRMATION,
            resolveActiveDialog(pending(), "提示", ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun alertBeatsReader() {
        assertEquals(
            ActiveDialog.WEB_VIEW_ALERT,
            resolveActiveDialog(null, "提示", ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun blankAlertTextStillClaimsAlertSlot() {
        // webViewAlert 的空串语义由写入方保证（alertText 兜底非空文案）——
        // 状态机只按「非 null 即挂起」裁决，空串不会被静默跳过
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, "", null))
    }
}

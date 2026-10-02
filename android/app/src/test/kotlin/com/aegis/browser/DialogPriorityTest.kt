package com.aegis.browser

import android.webkit.WebView
import com.aegis.broker.ApprovalRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import org.mockito.Mockito.mock
import kotlin.time.Clock
import com.aegis.browser.WebViewAlertNotice.Kind as AlertKind

/**
 * AD-151（审计 2026-09-23 清单·A7 批）：对话框单槽状态机优先级锁定——
 * 三对话框（待审批导航确认 / WebView 安全提示 / 阅读模式）同刻非空时
 * 只允许呈现安全优先级最高者；全空时无对话框。任何一处优先级倒置
 * （如提示遮蔽审批框——误 dismiss 即导航阻断）在此失败。
 */
class DialogPriorityTest {
    /** AD-260：一般安全提示（单按钮分型）构造器。 */
    private fun securityNotice(text: String = "提示") = WebViewAlertNotice(text, AlertKind.SECURITY_NOTICE)

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
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, securityNotice(), null))
        assertEquals(
            ActiveDialog.READER_CONTENT,
            resolveActiveDialog(null, null, ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun pendingConfirmationBeatsAlertAndReader() {
        assertEquals(
            ActiveDialog.PENDING_CONFIRMATION,
            resolveActiveDialog(pending(), securityNotice(), ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun alertBeatsReader() {
        assertEquals(
            ActiveDialog.WEB_VIEW_ALERT,
            resolveActiveDialog(null, securityNotice(), ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun blankAlertTextStillClaimsAlertSlot() {
        // webViewAlert 的空串语义由写入方保证（alertText 兜底非空文案）——
        // 状态机只按「非 null 即挂起」裁决，空串不会被静默跳过
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, securityNotice(""), null))
    }

    // ---------------- AD-260（2026-10-01 审计）：提示分型语义 ----------------

    @Test
    fun versionCheckAndSecurityNoticeAreDistinctKinds() {
        val version = WebViewAlertNotice("版本过旧", WebViewAlertNotice.Kind.VERSION_CHECK)
        val security = securityNotice("导航被拒")
        assertEquals(WebViewAlertNotice.Kind.VERSION_CHECK, version.kind)
        assertEquals(WebViewAlertNotice.Kind.SECURITY_NOTICE, security.kind)
        // 两种分型都占用同一对话框槽位（优先级不因分型改变）
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, version, null))
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, security, null))
    }

    // ---------------- AD-261（2026-10-01 审计）：分段代理对安全 ----------------

    @Test
    fun chunkingNeverSplitsSurrogatePairs() {
        // emoji（增补字符）铺满长文本：任何切点不得落在代理对中间——
        // 分段结果重组必须与原文逐字符一致（无孤立代理）。
        val emoji = "😀".repeat(500) // 每个占 2 个 UTF-16 char，切点必然命中代理对
        val chunks = chunkTextAtCharBoundary(emoji, 7)
        assertEquals(emoji, chunks.joinToString(""))
        chunks.forEach { chunk ->
            assertFalse(
                "分段边界劈开代理对（段尾不得是孤立高代理）",
                chunk.isNotEmpty() && Character.isHighSurrogate(chunk.last()),
            )
        }

        // 混合文本（ASCII + 增补 + BMP 汉字）重组一致性
        val mixed = ("ab😀😀汉字😀cd").repeat(100)
        val mixedChunks = chunkTextAtCharBoundary(mixed, 13)
        assertEquals(mixed, mixedChunks.joinToString(""))
    }

    @Test
    fun chunkingMatchesChunkedForAsciiText() {
        // ASCII 文本行为与 String.chunked 一致（无代理对时零差异）
        assertEquals(
            "abcdefghij".chunked(4),
            chunkTextAtCharBoundary("abcdefghij", 4),
        )
        assertEquals(
            listOf("abc"),
            chunkTextAtCharBoundary("abc", 4),
        )
    }
}

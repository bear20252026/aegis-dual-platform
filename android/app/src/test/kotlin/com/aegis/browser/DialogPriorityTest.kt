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

    /** AD-331：待确认下载构造器（continuation 空实现——状态机只看非 null）。 */
    private fun pendingDownload(url: String = "https://example.com/dl?file=x.exe") =
        PendingDownloadConfirmation(
            webView = mock(WebView::class.java),
            url = url,
            continuation = {},
        )

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
        assertNull(resolveActiveDialog(null, null, null, null))
    }

    @Test
    fun singleStatesResolveToTheirOwnSlot() {
        assertEquals(ActiveDialog.PENDING_CONFIRMATION, resolveActiveDialog(pending(), null, null, null))
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, null, securityNotice(), null))
        assertEquals(
            ActiveDialog.READER_CONTENT,
            resolveActiveDialog(null, null, null, ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun pendingConfirmationBeatsAlertAndReader() {
        assertEquals(
            ActiveDialog.PENDING_CONFIRMATION,
            resolveActiveDialog(pending(), null, securityNotice(), ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun alertBeatsReader() {
        assertEquals(
            ActiveDialog.WEB_VIEW_ALERT,
            resolveActiveDialog(null, null, securityNotice(), ReaderContent(title = "标题", text = "正文")),
        )
    }

    @Test
    fun blankAlertTextStillClaimsAlertSlot() {
        // webViewAlert 的空串语义由写入方保证（alertText 兜底非空文案）——
        // 状态机只按「非 null 即挂起」裁决，空串不会被静默跳过
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, null, securityNotice(""), null))
    }

    // ---------------- AD-260（2026-10-01 审计）：提示分型语义 ----------------

    @Test
    fun versionCheckAndSecurityNoticeAreDistinctKinds() {
        val version = WebViewAlertNotice("版本过旧", WebViewAlertNotice.Kind.VERSION_CHECK)
        val security = securityNotice("导航被拒")
        assertEquals(WebViewAlertNotice.Kind.VERSION_CHECK, version.kind)
        assertEquals(WebViewAlertNotice.Kind.SECURITY_NOTICE, security.kind)
        // 两种分型都占用同一对话框槽位（优先级不因分型改变）
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, null, version, null))
        assertEquals(ActiveDialog.WEB_VIEW_ALERT, resolveActiveDialog(null, null, security, null))
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

    // ---------------- AD-331（2026-10-02 审计）：下载确认槽位 ----------------

    @Test
    fun downloadConfirmationBeatsAlertAndReaderButNotNavigation() {
        // 安全优先级：导航审批 > 下载确认 > 安全提示 > 阅读模式
        assertEquals(
            ActiveDialog.PENDING_CONFIRMATION,
            resolveActiveDialog(pending(), pendingDownload(), securityNotice(), ReaderContent(title = "t", text = "x")),
        )
        assertEquals(
            ActiveDialog.DOWNLOAD_CONFIRMATION,
            resolveActiveDialog(null, pendingDownload(), securityNotice(), ReaderContent(title = "t", text = "x")),
        )
        assertEquals(ActiveDialog.DOWNLOAD_CONFIRMATION, resolveActiveDialog(null, pendingDownload(), null, null))
    }

    // ---------------- AD-300（2026-10-02 审计）：indices-1 语义修复回归 ----------------

    @Test
    fun chunkBoundarySurrogateAtInteriorSegmentIsMovedToNextChunk() {
        // 构造位置 2*chunkSize-1 恰为高代理：原 `raw.indices - 1`（Iterable.minus
        // 移除元素 1）使分段 1 的边界代理对永不迁移——重组出现孤立代理。
        // chunkSize=4：下标 7 为高代理（第二段段尾），其低代理落入第三段；
        // 迁移后第三段 = 高代理 + 原第三段（低代理 + 'C'）——共 3 段。
        val text = "AAAABBB\uD83C\uDF14C"
        val chunks = chunkTextAtCharBoundary(text, 4)
        assertEquals(text, chunks.joinToString(""))
        assertEquals(listOf("AAAA", "BBB", "\uD83C\uDF14C"), chunks)
        chunks.dropLast(1).forEach { chunk ->
            assertFalse(
                "非末段段尾不得是孤立高代理",
                chunk.isNotEmpty() && Character.isHighSurrogate(chunk.last()),
            )
        }
    }

    @Test
    fun chunkLastSegmentEndingWithHighSurrogateDoesNotThrow() {
        // 末段以孤立高代理结尾（其后无低代理——畸形输入）：原实现末段参与
        // 循环导致 raw[i+1] 越界（IndexOutOfBounds）。修复后末段不再检查。
        val text = "ABCDEFGH\uD83C" // 8 字符 + 孤立高代理 = 9
        val chunks = chunkTextAtCharBoundary(text, 4)
        assertEquals(listOf("ABCD", "EFGH", "\uD83C"), chunks)
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

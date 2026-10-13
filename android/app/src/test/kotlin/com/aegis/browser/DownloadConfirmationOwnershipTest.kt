package com.aegis.browser

import android.webkit.WebView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito.mock
import java.io.File

/**
 * AX-07（外部第三轮审计 2026-10-11 = 第九轮 §五 Q6 / R9-AD-6）：危险下载确认的
 * **授权归属**。用户在标签 A 上批准的那个 `.exe`，不能在切到标签 B 之后被 B 的
 * 确认框消费掉——导航确认从一开始就有这道校验（AD-158），下载确认只做到了
 * 「单槽 + 消费一次」，缺的正是同一半边。
 *
 * 两面都钉：
 * - 行为面：归属不符 ⇒ 不 `proceed()`、**不清槽**（回原标签仍可确认，与导航同口径）、
 *   给切回提示；
 * - 装配面：`newTab`/`switchTo` 必须撤销 pending 下载（既有撤销只覆盖导航确认，
 *   `closeTab` 只覆盖被关闭的那个标签）。
 *
 * 装配面走源码文本锚（[DocumentStartInjectionRegressionTest] 同款口径）：这两条要经
 * 真实 `TabManager` + `createSecureWebView` 才可达，在 JVM 里搭出标签生命周期比锚本身
 * 更脆；文本锚按有界切片 + 剔注释判，正向控制是「同一切片里必须同时看得见导航撤销」。
 */
class DownloadConfirmationOwnershipTest {
    private class Fixture {
        var current: WebView? = null
        var proceeded = 0
        var noticeId: Int? = null

        val confirmations =
            BrowserViewModelConfirmations(
                currentWebView = { current },
                resolveText = { id ->
                    noticeId = id
                    "notice-$id"
                },
            )

        fun registerOn(owner: WebView) =
            confirmations.registerPendingDownload(
                webView = owner,
                url = "https://example.com/setup.exe",
                proceed = { proceeded++ },
            )
    }

    @Test
    fun originatingTabConsumesItsOwnConfirmationOnce() {
        val f = Fixture()
        val tabA = mock(WebView::class.java)
        f.current = tabA
        f.registerOn(tabA)

        f.confirmations.approvePendingDownload()
        assertEquals(1, f.proceeded)
        assertNull(f.confirmations.pendingDownloadConfirmation.value)

        // 重复点击/dialog 复现 = no-op（AD-331 的单次消费语义不许被归属校验改掉）
        f.confirmations.approvePendingDownload()
        assertEquals(1, f.proceeded)
    }

    @Test
    fun approvalFromAnotherTabNeitherProceedsNorClearsThePendingSlot() {
        val f = Fixture()
        val tabA = mock(WebView::class.java)
        val tabB = mock(WebView::class.java)
        f.registerOn(tabA)
        f.current = tabB

        f.confirmations.approvePendingDownload()

        assertEquals(0, f.proceeded)
        assertEquals(R.string.confirm_switch_back, f.noticeId)
        assertNotNull(f.confirmations.pendingDownloadConfirmation.value)
    }

    @Test
    fun returningToTheOriginatingTabMakesTheSamePendingItemApprovable() {
        val f = Fixture()
        val tabA = mock(WebView::class.java)
        val tabB = mock(WebView::class.java)
        f.registerOn(tabA)
        f.current = tabB
        f.confirmations.approvePendingDownload()
        assertEquals(0, f.proceeded)

        f.current = tabA
        f.confirmations.approvePendingDownload()
        assertEquals(1, f.proceeded)
        assertNull(f.confirmations.pendingDownloadConfirmation.value)
    }

    @Test
    fun rejectionStillDropsThePendingDownloadWithoutProceeding() {
        // 反向控制：新加的归属判定不许把「拒绝」这条路变成「保留待确认」
        val f = Fixture()
        f.current = mock(WebView::class.java)
        f.registerOn(mock(WebView::class.java))

        f.confirmations.rejectPendingDownload()

        assertEquals(0, f.proceeded)
        assertNull(f.confirmations.pendingDownloadConfirmation.value)
    }

    @Test
    fun closingAnUnrelatedTabKeepsThePendingDownload() {
        val f = Fixture()
        val tabA = mock(WebView::class.java)
        val tabB = mock(WebView::class.java)
        f.registerOn(tabA)

        f.confirmations.resolvePendingDownload(tabB)
        assertNotNull(f.confirmations.pendingDownloadConfirmation.value)

        f.confirmations.resolvePendingDownload(tabA)
        assertNull(f.confirmations.pendingDownloadConfirmation.value)
    }

    @Test
    fun tabLifecycleCancelsPendingDownloadsTheWayItCancelsPendingNavigations() {
        val code = codeOf(TABS_SOURCE)
        for (declaration in listOf("fun newTab(", "fun switchTo(")) {
            val body = bodyOf(code, declaration)
            assertNotNull("未找到 $declaration——BrowserViewModelTabs 形态已改，本锚需同步改写", body)
            // 正向控制：同一张切片里先看得见导航撤销，才说明这条锚判的是那段代码
            assertTrue(
                "$declaration 连导航撤销都不见了——切片取错，本锚失效",
                body!!.contains("confirmations.rejectPendingNavigationConfirmation()"),
            )
            assertTrue(
                "$declaration 未撤销 pending 下载：切换标签后旧标签的危险下载确认可被前台标签批准（AX-07）",
                body.contains("confirmations.rejectPendingDownload()"),
            )
        }
        // closeTab 走归属式撤销（只清被关闭标签那一条），不许被改成全清
        val close = bodyOf(code, "fun closeTab(")
        assertNotNull(close)
        assertTrue(close!!.contains("confirmations.resolvePendingDownload(tab.webView)"))
    }

    @Test
    fun downloadApprovalSharesTheNavigationOwnershipSeam() {
        val code = codeOf(CONFIRMATIONS_SOURCE)
        val download = bodyOf(code, "fun approvePendingDownload()")
        assertNotNull(download)
        // 判据必须落在同一个 currentWebView 缝上——另起一份「活动标签」定义就是第二个判据源
        assertTrue(download!!.contains("currentWebView() !== pending.webView"))
        assertTrue(code.contains("fun approvePendingNavigationConfirmation()"))
    }

    private companion object {
        const val TABS_SOURCE =
            "android/app/src/main/java/com/aegis/browser/BrowserViewModelTabs.kt"
        const val CONFIRMATIONS_SOURCE =
            "android/app/src/main/java/com/aegis/browser/BrowserViewModelConfirmations.kt"

        /** 剔注释后的源码：口径单源在 `withoutComments()`（R9-B45 / 台账 Q59）——
         *  本仓注记常抄旧形态原文，不剔会被自己的注释打红。 */
        fun codeOf(relative: String): String {
            val file = File(repoRoot(), relative)
            assertTrue("锚语料缺失：$relative", file.exists())
            return file
                .readText()
                .replace("\r\n", "\n")
                .withoutComments()
        }

        /** 有界切片：从声明行到下一个同级 `fun `（越界即退化成全文扫描，那是旧锚的病）。 */
        fun bodyOf(
            code: String,
            declaration: String,
        ): String? {
            val start = code.indexOf(declaration)
            if (start < 0) return null
            val rest = code.substring(start + declaration.length)
            val next = rest.indexOf("\n    fun ")
            return if (next < 0) rest else rest.substring(0, next)
        }

        fun repoRoot(): File {
            var dir: File? = File(System.getProperty("user.dir")).absoluteFile
            while (dir != null) {
                if (File(dir, TABS_SOURCE).exists()) return dir
                dir = dir.parentFile
            }
            error("未在仓库内运行（找不到 $TABS_SOURCE）")
        }
    }
}

package com.aegis.browser

import android.net.http.SslError
import android.webkit.WebViewClient
import com.aegis.webviewadapter.WebViewErrorCodes
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * AD-103 配套（审计 2026-09-23 清单·A6 批）：PageErrorTexts 映射矩阵单测——
 * 错误码→面板文案映射随 AD-103 抽出后锁定（资源 id 经 FakeStrings 注入，
 * 断言「文案 = 资源 id」组合而非具体中文，重命名文案不断测试）。
 */
class PageErrorTextsTest {
    /** 资源 id 直通假实现：text(id)="s{id}"、text(id,arg)="s{id}({arg})"。 */
    private val fake =
        object : PageErrorTexts.Strings {
            override fun text(id: Int): String = "s$id"

            override fun text(
                id: Int,
                arg: String,
            ): String = "s$id($arg)"
        }

    @Test
    fun sslCodeMapsPrimaryErrorToNamedResource() {
        val rendered =
            PageErrorTexts.textFor(
                WebViewErrorCodes.ERROR_SSL_CERTIFICATE,
                SslError.SSL_EXPIRED.toString(),
                fake,
            )
        assertEquals("s${R.string.page_error_ssl}(s${R.string.ssl_name_expired})", rendered)
    }

    @Test
    fun sslUnknownPrimaryErrorFallsBackToUnknownResource() {
        val rendered =
            PageErrorTexts.textFor(
                WebViewErrorCodes.ERROR_SSL_CERTIFICATE,
                "9999",
                fake,
            )
        assertEquals("s${R.string.page_error_ssl}(s${R.string.ssl_name_unknown})", rendered)
    }

    @Test
    fun httpCodePassesStatusCodeThrough() {
        assertEquals(
            "s${R.string.page_error_http}(503)",
            PageErrorTexts.textFor(WebViewErrorCodes.ERROR_HTTP, "503", fake),
        )
    }

    @Test
    fun mainFrameKnownErrorMapsToNamedResource() {
        val rendered =
            PageErrorTexts.textFor(
                WebViewErrorCodes.ERROR_MAIN_FRAME,
                "${WebViewClient.ERROR_HOST_LOOKUP}:net::ERR_NAME_NOT_RESOLVED",
                fake,
            )
        assertEquals("s${R.string.page_error_main_frame}(s${R.string.err_name_host_lookup})", rendered)
    }

    @Test
    fun mainFrameUnknownErrorPassesRawDescription() {
        val rendered =
            PageErrorTexts.textFor(
                WebViewErrorCodes.ERROR_MAIN_FRAME,
                "-1:some vendor specific failure",
                fake,
            )
        assertEquals(
            "s${R.string.page_error_main_frame}(some vendor specific failure)",
            rendered,
        )
    }

    @Test
    fun unrecognizedCodeFallsBackToRawDetail() {
        val rendered = PageErrorTexts.textFor("future_code", "原样透传", fake)
        assertEquals("原样透传", rendered)
    }

    // ---------------- AD-203（审计 2026-09-23 清单·A7 批）：deny code 映射表 ----------------

    @Test
    fun sessionExpiredDenyCodeMapsToDedicatedResource() {
        assertEquals(R.string.session_expired, PageErrorTexts.denyAlertTextRes("session_expired"))
    }

    @Test
    fun unknownDenyCodesFallBackToPolicyRejectedResource() {
        assertEquals(R.string.nav_rejected_code, PageErrorTexts.denyAlertTextRes("url_policy"))
        assertEquals(R.string.nav_rejected_code, PageErrorTexts.denyAlertTextRes("tab_mismatch"))
        assertEquals(R.string.nav_rejected_code, PageErrorTexts.denyAlertTextRes("future_native_code"))
    }
}

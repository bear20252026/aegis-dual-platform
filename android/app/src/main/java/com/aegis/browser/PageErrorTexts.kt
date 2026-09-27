package com.aegis.browser

import android.net.http.SslError
import android.webkit.WebViewClient
import com.aegis.webviewadapter.WebViewErrorCodes

/**
 * AD-103（审计 2026-09-23 清单·A6 批）：页面错误码 → 面板文案映射单文件
 * （原 BrowserViewModel 内三个私有映射函数随文件拆分抽出；AD-035 的
 * 「文案映射收敛在 app 层单源」语义不变）。
 *
 * 资源解析经 [Strings] 函数化注入——本对象零 Android Context 依赖，
 * 映射矩阵可 JVM 单测直测。
 */
internal object PageErrorTexts {
    /** 错误文案资源解析接缝（appContext.getString 的函数化；双方法——SAM
     *  不可用，调用方以 object 表达式实现）。 */
    interface Strings {
        fun text(id: Int): String

        fun text(
            id: Int,
            arg: String,
        ): String
    }

    /** AD-035：webview-adapter 错误码 → 面板文案（未识别码回退原始 detail）。 */
    fun textFor(
        code: String,
        detail: String,
        strings: Strings,
    ): String =
        when (code) {
            WebViewErrorCodes.ERROR_SSL_CERTIFICATE -> {
                strings.text(R.string.page_error_ssl, strings.text(sslNameRes(detail.toIntOrNull())))
            }

            WebViewErrorCodes.ERROR_HTTP -> {
                strings.text(R.string.page_error_http, detail)
            }

            WebViewErrorCodes.ERROR_MAIN_FRAME -> {
                val errorCode = detail.substringBefore(':').toIntOrNull()
                val rawDescription = detail.substringAfter(':', missingDelimiterValue = "")
                strings.text(R.string.page_error_main_frame, mainFrameErrorName(errorCode, rawDescription, strings))
            }

            else -> {
                detail
            }
        }

    /** SslError.primaryError → 资源 id（未识别回退「未知证书错误」）。 */
    fun sslNameRes(primaryError: Int?): Int =
        when (primaryError) {
            SslError.SSL_DATE_INVALID -> R.string.ssl_name_date_invalid
            SslError.SSL_EXPIRED -> R.string.ssl_name_expired
            SslError.SSL_IDMISMATCH -> R.string.ssl_name_id_mismatch
            SslError.SSL_NOTYETVALID -> R.string.ssl_name_not_yet_valid
            SslError.SSL_UNTRUSTED -> R.string.ssl_name_untrusted
            SslError.SSL_INVALID -> R.string.ssl_name_invalid
            else -> R.string.ssl_name_unknown
        }

    /** 主框架错误码 → 文案（ERROR_* 常量单源在 WebViewErrorCodes；未识别回退原始描述）。 */
    fun mainFrameErrorName(
        errorCode: Int?,
        description: String,
        strings: Strings,
    ): String =
        when (errorCode) {
            WebViewClient.ERROR_HOST_LOOKUP -> strings.text(R.string.err_name_host_lookup)
            WebViewClient.ERROR_CONNECT -> strings.text(R.string.err_name_connect)
            WebViewClient.ERROR_TIMEOUT -> strings.text(R.string.err_name_timeout)
            WebViewClient.ERROR_UNSUPPORTED_SCHEME -> strings.text(R.string.err_name_unsupported_scheme)
            else -> description.ifBlank { strings.text(R.string.err_name_fallback) }
        }
}

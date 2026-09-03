package com.aegis.browser

import android.app.DownloadManager
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.WebView

/**
 * WebView 下载统一处理（单文件单职责：从 SecureWebViewFactory 拆出——H-6）。
 *
 * - 仅放行 http/https（DownloadManager 不支持 blob/data 等 scheme）；
 * - 危险扩展（exe/bat/apk 等——DownloadPolicy 白名单反查）直接拦截
 *   并以 Toast 明示用户，绝不静默放行；
 * - 其余交系统 DownloadManager（带会话 Cookie）。
 */
internal object WebViewDownloadHandler {
    fun handleDownload(
        webView: WebView,
        url: String,
        mimeType: String,
        contentDisposition: String,
    ) {
        val context = webView.context
        val scheme =
            android.net.Uri
                .parse(url)
                .scheme
                ?.lowercase()
        if (scheme != "http" && scheme != "https") {
            android.util.Log.w("AegisDownload", "拦截非 http(s) 下载: $scheme")
            android.widget.Toast
                .makeText(context, "已拦截不支持的下载类型", android.widget.Toast.LENGTH_SHORT)
                .show()
            return
        }
        if (DownloadPolicy.requiresExplicitConfirmation(url)) {
            android.util.Log.w("AegisDownload", "拦截危险扩展下载: $url")
            android.widget.Toast
                .makeText(context, "已拦截危险文件类型的下载", android.widget.Toast.LENGTH_LONG)
                .show()
            return
        }
        val fileName = resolveDownloadFileName(url, contentDisposition, mimeType)
        val request =
            DownloadManager
                .Request(android.net.Uri.parse(url))
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
                .setMimeType(mimeType)
        CookieManager.getInstance().getCookie(url)?.let { request.addRequestHeader("Cookie", it) }
        runCatching {
            context.getSystemService(DownloadManager::class.java).enqueue(request)
            android.widget.Toast
                .makeText(context, "开始下载：$fileName", android.widget.Toast.LENGTH_SHORT)
                .show()
        }.onFailure {
            android.util.Log.e("AegisDownload", "下载入队失败: ${it.message}")
            android.widget.Toast
                .makeText(context, "下载失败，无法入队下载管理器", android.widget.Toast.LENGTH_SHORT)
                .show()
        }
    }

    /** 下载文件名解析优先级：Content-Disposition → URL 路径段 → 时间戳兜底。 */
    private fun resolveDownloadFileName(
        url: String,
        mimeType: String,
        contentDisposition: String,
    ): String =
        contentDisposition
            .substringAfter("filename=", "")
            .trim(' ', '"', ';')
            .takeIf { it.isNotEmpty() }
            ?: android.net.Uri
                .parse(url)
                .lastPathSegment
                ?.takeIf { it.isNotBlank() }
            ?: "aegis-download-${System.currentTimeMillis()}.${mimeType.substringAfter('/', "").ifEmpty { "bin" }}"
}

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
    /** P2-5 修复（全面审计 2026-09-04）：净化失败的默认下载名（无扩展名）。 */
    private const val DEFAULT_DOWNLOAD_NAME = "aegis_download"

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
        // P2-5 修复：文件名先解析（净化后）再判定危险扩展——`/download?file=x.exe`
        // 类直链的文件名在 Content-Disposition，判定需要拿到净化后文件名。
        val fileName = resolveDownloadFileName(url, mimeType, contentDisposition)
        if (DownloadPolicy.requiresExplicitConfirmation(url, fileName)) {
            android.util.Log.w("AegisDownload", "拦截危险扩展下载: $url")
            android.widget.Toast
                .makeText(context, "已拦截危险文件类型的下载", android.widget.Toast.LENGTH_LONG)
                .show()
            return
        }
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

    /**
     * 下载文件名解析（P2-5 修复（全面审计 2026-09-04））：
     * Content-Disposition filename → URL 路径段 → [DEFAULT_DOWNLOAD_NAME] 兜底；
     * 全部经 [sanitizeFileName] 净化（服务器文件名可含 `/`、`\`、`..` 段与
     * 控制字符——原实现直接拼 setDestinationInExternalPublicDir 存在路径
     * 穿越/文件覆盖风险）；净化失败回退默认名。扩展名缺失时从 mimetype 或
     * URL 推断，推断不出不加。
     */
    private fun resolveDownloadFileName(
        url: String,
        mimeType: String,
        contentDisposition: String,
    ): String {
        val uri = android.net.Uri.parse(url)
        val fromDisposition =
            contentDisposition
                .substringAfter("filename=", "")
                .trim(' ', '"', ';')
        val base =
            sanitizeFileName(fromDisposition)
                ?: sanitizeFileName(uri.lastPathSegment.orEmpty())
                ?: DEFAULT_DOWNLOAD_NAME
        val extension =
            base
                .substringAfterLast('.', missingDelimiterValue = "")
                .takeIf { it.isNotBlank() }
                ?: inferExtension(uri, mimeType)
        // 组合名兜底再净化一次（推断出的扩展名也可能携带分隔符）
        return extension?.let { "$base.$it" }?.let { sanitizeFileName(it) } ?: base
    }

    /**
     * P2-5 修复（全面审计 2026-09-04）：文件名净化——剥离路径分隔符（`/`
     * 与 `\`，只取最后一段）、拒绝 `..` 段、去除控制字符与首尾空白及尾部
     * 空点（`x.exe.` → `x.exe`）；净化失败（空结果）返回 null。
     */
    private fun sanitizeFileName(raw: String): String? =
        raw
            .substringAfterLast('/')
            .substringAfterLast('\\')
            .filterNot { it.isISOControl() }
            .trim()
            .trimEnd('.')
            .takeIf { it.isNotBlank() }

    /** P2-5 修复：扩展名推断——mimetype 子类型优先，URL 路径段次之；推断不出返回 null（不加扩展名）。 */
    private fun inferExtension(
        uri: android.net.Uri,
        mimeType: String,
    ): String? {
        sanitizeFileName(mimeType.substringAfter('/', ""))?.let { return it }
        return sanitizeFileName(uri.lastPathSegment.orEmpty().substringAfterLast('.', ""))
    }
}

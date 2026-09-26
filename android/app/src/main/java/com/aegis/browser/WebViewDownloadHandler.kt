package com.aegis.browser

import android.app.DownloadManager
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.WebView
import com.aegis.webviewadapter.LogRedact

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

    /**
     * AD-032（2026-09-24 审计）：下载文件名长度上限。超长文件名（服务器可控）
     * 会导致 DownloadManager 落盘失败/通知栏渲染异常——截断基本名、保留扩展名。
     */
    private const val MAX_DOWNLOAD_NAME_LENGTH = 200

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
            // AD-220（2026-09-26 审计）：下载日志统一接入脱敏单源——此前两处
            // Log.w 明文记录完整 URL（含 query 的 token），LogRedact 为
            // webview-adapter internal 无法跨模块复用，现已 public 化。
            android.util.Log.w("AegisDownload", "拦截危险扩展下载: ${LogRedact.redact(url)}")
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
     *
     * AD-027（2026-09-24 审计）：URL 路径段提取纯字符串化（fragment/query
     * 剥离后取末段——与 Uri.getLastPathSegment 对 http(s) 直链语义一致），
     * JVM 单测不再依赖 android.net.Uri。
     */
    internal fun resolveDownloadFileName(
        url: String,
        mimeType: String,
        contentDisposition: String,
    ): String {
        // AD-217（2026-09-26 审计）：URL 路径段先百分号解码再取尾段（与
        // DownloadPolicy 判定口径一致——`/dl/malware%2Eexe` 此前不解码）。
        val urlPathSegment =
            decodePercent(url.substringBefore('#').substringBefore('?'))
                .substringAfterLast('/')
        val fromDisposition = resolveDispositionFileName(contentDisposition)
        val base =
            sanitizeFileName(fromDisposition)
                ?: sanitizeFileName(urlPathSegment)
                ?: DEFAULT_DOWNLOAD_NAME
        // AD-027 配套缺陷修复（2026-09-24 写测试暴露）：原实现对已带扩展名的
        // base 仍追加推断扩展名（report.pdf → report.pdf.pdf）。现仅在 base
        // 无扩展名时才从 mimetype/URL 推断追加；组合名兜底再净化一次。
        val hasExtension = base.substringAfterLast('.', missingDelimiterValue = "").isNotBlank()
        val resolved =
            if (hasExtension) {
                base
            } else {
                inferExtension(urlPathSegment, mimeType)
                    ?.let { "$base.$it" }
                    ?.let { sanitizeFileName(it) }
                    ?: base
            }
        return capLength(resolved)
    }

    /**
     * AD-032：超长文件名截断——基本名按上限截断、扩展名保留
     * （`<200 字符基本名>.pdf` 而非把 `.pdf` 切掉变成无类型文件）。
     * 截断后基本名可能以点结尾 → 再净化一次（trimEnd('.')）。
     */
    private fun capLength(name: String): String =
        when {
            name.length <= MAX_DOWNLOAD_NAME_LENGTH -> {
                name
            }

            else -> {
                val extension = name.substringAfterLast('.', missingDelimiterValue = "")
                if (extension.isBlank() || extension.length >= MAX_DOWNLOAD_NAME_LENGTH) {
                    name.take(MAX_DOWNLOAD_NAME_LENGTH).trimEnd('.')
                } else {
                    val baseBudget = MAX_DOWNLOAD_NAME_LENGTH - extension.length - 1
                    name.dropLast(extension.length + 1).take(baseBudget).trimEnd('.') + "." + extension
                }
            }
        }

    /**
     * AD-230（2026-09-26 审计）：Content-Disposition 文件名解析——此前只认
     * 小写字面 `filename=`：RFC 5987 `filename*=UTF-8''…`（非 ASCII 文件名的
     * 标准形态）与大小写变体（`FileName=`）全部漏解析。优先 filename*
     * （剥 charset 前缀后百分号解码），回退 filename（大小写不敏感）；
     * 均未命中返回空串（交由后续 URL/默认名兜底）。
     */
    internal fun resolveDispositionFileName(contentDisposition: String): String {
        val starred =
            Regex("filename\\*=([^;]+)", RegexOption.IGNORE_CASE)
                .find(contentDisposition)
                ?.groupValues
                ?.get(1)
                ?.trim()
        if (!starred.isNullOrBlank()) {
            // RFC 5987 形如 `UTF-8''%E6%8A%A5.pdf`——剥 charset'' 前缀后解码；
            // 无前缀（裸百分号编码）按原串处理
            val encoded = starred.substringAfter("''", missingDelimiterValue = starred)
            return decodePercent(encoded)
        }
        return Regex("filename=([^;]+)", RegexOption.IGNORE_CASE)
            .find(contentDisposition)
            ?.groupValues
            ?.get(1)
            ?.trim(' ', '"', ';')
            .orEmpty()
    }

    /** AD-230/AD-217 配套：百分号解码；非法编码原样返回（fail-closed）。 */
    private fun decodePercent(raw: String): String =
        try {
            java.net.URLDecoder.decode(raw, "UTF-8")
        } catch (_: IllegalArgumentException) {
            raw
        } catch (_: java.io.UnsupportedEncodingException) {
            raw
        }

    /**
     * P2-5 修复（全面审计 2026-09-04）：文件名净化——剥离路径分隔符（`/`
     * 与 `\`，只取最后一段）、拒绝 `..` 段、去除控制字符与首尾空白及尾部
     * 空点（`x.exe.` → `x.exe`）；净化失败（空结果）返回 null。
     */
    internal fun sanitizeFileName(raw: String): String? =
        raw
            .substringAfterLast('/')
            .substringAfterLast('\\')
            .filterNot { it.isISOControl() }
            .trim()
            .trimEnd('.')
            .takeIf { it.isNotBlank() }

    /** P2-5 修复：扩展名推断——mimetype 子类型优先，URL 路径段次之；推断不出返回 null（不加扩展名）。 */
    private fun inferExtension(
        urlPathSegment: String,
        mimeType: String,
    ): String? {
        sanitizeFileName(mimeType.substringAfter('/', ""))?.let { return it }
        return sanitizeFileName(urlPathSegment.substringAfterLast('.', ""))
    }
}

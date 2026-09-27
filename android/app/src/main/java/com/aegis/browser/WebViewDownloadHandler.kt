package com.aegis.browser

import android.app.DownloadManager
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.WebView
import android.widget.Toast
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

    /**
     * AD-138（审计 2026-09-23 清单·A6 批）：mimetype → 扩展名白名单映射——
     * 原实现把 mime 子类型直接当扩展名（application/x-msdownload →
     * "x-msdownload"、text/plain → "plain"、application/octet-stream →
     * "octet-stream"），产出无意义/错误后缀文件。仅登记常见 mime 的正确
     * 映射，未命中回落 URL 路径段、再推不出不加后缀。
     */
    private val MIME_EXTENSIONS =
        mapOf(
            "application/pdf" to "pdf",
            "application/zip" to "zip",
            "application/x-zip-compressed" to "zip",
            "application/gzip" to "gz",
            "application/x-tar" to "tar",
            "application/vnd.android.package-archive" to "apk",
            "application/msword" to "doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document" to "docx",
            "application/vnd.ms-excel" to "xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" to "xlsx",
            "application/vnd.ms-powerpoint" to "ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation" to "pptx",
            "text/plain" to "txt",
            "text/csv" to "csv",
            "text/html" to "html",
            "image/png" to "png",
            "image/jpeg" to "jpg",
            "image/gif" to "gif",
            "image/webp" to "webp",
            "audio/mpeg" to "mp3",
            "audio/mp4" to "m4a",
            "audio/ogg" to "ogg",
            "audio/wav" to "wav",
            "video/mp4" to "mp4",
            "video/webm" to "webm",
        )

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
                .makeText(context, context.getString(R.string.download_blocked_type), android.widget.Toast.LENGTH_SHORT)
                .show()
            return
        }
        // P2-5 修复：文件名先解析（净化后）再判定危险扩展——`/download?file=x.exe`
        // 类直链的文件名在 Content-Disposition，判定需要拿到净化后文件名。
        val fileName = resolveDownloadFileName(url, mimeType, contentDisposition)
        if (DownloadPolicy.requiresExplicitConfirmation(url, fileName)) {
            // AD-220（2026-09-26 审计）：下载日志统一接入脱敏单源。
            android.util.Log.w("AegisDownload", "拦截危险扩展下载: ${LogRedact.redact(url)}")
            Toast
                .makeText(context, context.getString(R.string.download_blocked_dangerous), Toast.LENGTH_LONG)
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
        // AD-137（审计 2026-09-23 清单·A6 批）：成功 Toast 与受守护调用分离——
        // 原实现成功 Toast 在 runCatching 块内，Toast 抛出会被误判为入队失败
        // （双 Toast 叠加且误导日志）；onSuccess/onFailure 分离后各归其位。
        runCatching {
            context.getSystemService(DownloadManager::class.java).enqueue(request)
        }.onSuccess {
            Toast
                .makeText(context, context.getString(R.string.download_started, fileName), Toast.LENGTH_SHORT)
                .show()
        }.onFailure {
            android.util.Log.e("AegisDownload", "下载入队失败: ${it.message}")
            Toast
                .makeText(context, context.getString(R.string.download_enqueue_failed), Toast.LENGTH_SHORT)
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

    /**
     * 扩展名推断（P2-5 修复引入；AD-138 改白名单映射）：mime 精确白名单
     * 优先，URL 路径段次之；推断不出返回 null（不加扩展名）。
     */
    private fun inferExtension(
        urlPathSegment: String,
        mimeType: String,
    ): String? {
        MIME_EXTENSIONS[mimeType.trim().lowercase()]?.let { return it }
        return sanitizeFileName(urlPathSegment.substringAfterLast('.', ""))
    }
}

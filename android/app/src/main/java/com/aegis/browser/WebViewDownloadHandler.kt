package com.aegis.browser

import android.app.DownloadManager
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.WebView
import android.widget.Toast
import com.aegis.webviewadapter.LogRedact

// AD-262/263：字节数上限与严格解码引入的私有助手使函数数超阈值——各函数均为单一解析职责

/**
 * WebView 下载统一处理（单文件单职责：从 SecureWebViewFactory 拆出——H-6）。
 *
 * - 仅放行 http/https（DownloadManager 不支持 blob/data 等 scheme）；
 * - 危险扩展（exe/bat/apk 等——DownloadPolicy 白名单反查）直接拦截
 *   并以 Toast 明示用户，绝不静默放行；
 * - 其余交系统 DownloadManager（带会话 Cookie）。
 *
 * AD-262/263（2026-10-01 审计）：字节数上限与严格解码引入的私有助手使
 * 函数数超 detekt 阈值——各函数均为单一解析职责。
 */
@Suppress("TooManyFunctions")
internal object WebViewDownloadHandler {
    /** P2-5 修复（全面审计 2026-09-04）：净化失败的默认下载名（无扩展名）。 */
    private const val DEFAULT_DOWNLOAD_NAME = "aegis_download"

    /**
     * AD-032（2026-09-24 审计）：下载文件名长度上限。超长文件名（服务器可控）
     * 会导致 DownloadManager 落盘失败/通知栏渲染异常——截断基本名、保留扩展名。
     */
    private const val MAX_DOWNLOAD_NAME_LENGTH = 200

    /**
     * AD-262（2026-10-01 审计）：文件名字节上限——200 字符截断 ≠ 字节上限：
     * 中文文件名 200 字符 = 600 UTF-8 字节，超出 ext4/FAT 文件系统单文件名
     * 255 字节上限，DownloadManager 落盘失败。240（< 255，留文件系统编码
     * 余量）按 UTF-8 字节度量截断，保扩展名；与字符上限（[MAX_DOWNLOAD_NAME_LENGTH]）
     * 双重约束（ASCII 名仍受 200 字符约束，行为不变）。
     */
    private const val MAX_DOWNLOAD_NAME_BYTES = 240

    /** AD-262/263 配套常量（detekt MagicNumber 命名化）。 */
    private const val UTF8_1_BYTE_MAX = 0x7F

    private const val UTF8_2_BYTE_MAX = 0x7FF

    private const val UTF8_3_BYTE_MAX = 0xFFFF

    private const val UTF8_3_BYTES = 3

    private const val UTF8_4_BYTES = 4

    private const val HEX_RADIX_OFFSET = 10

    private const val HEX_NIBBLE_SHIFT = 4

    /** `%XX` 转义全长（% + 两位十六进制）。 */
    private const val PERCENT_ESCAPE_LENGTH = 3

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
        // AD-331（2026-10-02 审计）：二级确认回调——仅查询参数命中危险扩展时
        // 调用；回调展示确认 UI，用户批准时调用 proceed() 继续入队，否则放弃
        // （fail-closed）。生产经 SecureWebViewFactory 接 MainDialogs 单槽。
        requestConfirmation: (proceed: () -> Unit) -> Unit = { proceed -> proceed() },
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
        // AD-331（2026-10-02 审计）：拆两级——路径/文件名命中硬拦截；仅查询
        // 参数命中经确认对话框放行（原 requiresExplicitConfirmation 名实不符：
        // 承诺确认、实现硬拦截）。
        if (DownloadPolicy.isHardBlocked(url, fileName)) {
            // AD-220（2026-09-26 审计）：下载日志统一接入脱敏单源。
            android.util.Log.w("AegisDownload", "拦截危险扩展下载: ${LogRedact.redact(url)}")
            Toast
                .makeText(context, context.getString(R.string.download_blocked_dangerous), Toast.LENGTH_LONG)
                .show()
            return
        }
        if (DownloadPolicy.requiresExplicitConfirmation(url, fileName)) {
            android.util.Log.w("AegisDownload", "危险扩展下载待确认（仅查询参数命中）: ${LogRedact.redact(url)}")
            requestConfirmation { enqueueDownload(context, url, mimeType, fileName) }
            return
        }
        enqueueDownload(context, url, mimeType, fileName)
    }

    /** AD-331：入队单源（确认续体与直通路径共用——参数已解析完毕）。 */
    private fun enqueueDownload(
        context: android.content.Context,
        url: String,
        mimeType: String,
        fileName: String,
    ) {
        val request =
            DownloadManager
                .Request(android.net.Uri.parse(url))
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                // AD-193（审计 2026-09-23 清单·A7 批）：通知标题/描述补齐——
                // 原请求未 setTitle/setDescription，通知栏回落为裸 URL（可读
                // 性差且泄露完整 query）。标题用净化后的文件名，描述用资源
                // 文案（strings.xml 单源）。
                .setTitle(fileName)
                .setDescription(context.getString(R.string.download_notification_description))
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
                .setMimeType(mimeType)
        // AD-194（审计 2026-09-23 清单·A7 批）：Cookie 过滤语义注释固化——
        // getCookie(url) 返回 CookieManager 为该 URL 维护的整套 cookie jar
        // 视图（与页面自身发起同源请求将携带的集合一致；WebView 层已按
        // A-03 拒绝第三方 cookie，此处不做二次过滤是有意为之：过滤集合
        // 反而会造成「页面可见资源可下载、带 Cookie 下载却缺凭证」的
        // 语义分叉）。DownloadManager 落盘期间经系统 download provider
        // 发起请求，Cookie 头以单次请求头形式随行，不写入持久存储。
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
        // AD-305（2026-10-02 审计）：路径段改 [decodePercentStrict]——路径中
        // `+` 是字面加号（RFC 3986 path 不含 query 的 `+`→空格语义），原
        // URLDecoder 把 `a+b.pdf` 解成 `a b.pdf`（文件名字面失真；与 AD-263
        // 的 RFC 5987 filename* 解码同口径）。
        val urlPathSegment =
            decodePercentStrict(url.substringBefore('#').substringBefore('?'))
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
     *
     * AD-262（2026-10-01 审计）：字符截断后追加字节截断（UTF-8 度量）——
     * CJK 文件名按字符数达标但按字节超文件系统 255 字节单名上限。
     */
    private fun capLength(name: String): String = capByteLength(capCharLength(name))

    private fun capCharLength(name: String): String =
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
     * AD-262：UTF-8 字节预算截断（码点安全——不劈代理对），保扩展名；
     * 扩展名自身超预算一半时放弃保留（畸形输入防呆）。空结果回退默认名。
     */
    private fun capByteLength(name: String): String {
        if (name.toByteArray(Charsets.UTF_8).size <= MAX_DOWNLOAD_NAME_BYTES) return name
        val dot = name.lastIndexOf('.')
        val keepExtension =
            dot > 0 && name.substring(dot).toByteArray(Charsets.UTF_8).size <= MAX_DOWNLOAD_NAME_BYTES / 2
        val extension = if (keepExtension) name.substring(dot) else ""
        val base = if (keepExtension) name.substring(0, dot) else name
        val budget = MAX_DOWNLOAD_NAME_BYTES - extension.toByteArray(Charsets.UTF_8).size
        val capped = StringBuilder()
        var usedBytes = 0
        val codePoints = base.codePoints().iterator()
        while (codePoints.hasNext()) {
            val codePoint = codePoints.nextInt()
            val codePointBytes = utf8ByteCount(codePoint)
            if (usedBytes + codePointBytes > budget) break
            capped.appendCodePoint(codePoint)
            usedBytes += codePointBytes
        }
        return capped
            .toString()
            .trimEnd('.')
            .plus(extension)
            .ifBlank { DEFAULT_DOWNLOAD_NAME }
    }

    /** AD-262：码点 → UTF-8 字节数（RFC 3629 定长表）。 */
    private fun utf8ByteCount(codePoint: Int): Int =
        when {
            codePoint <= UTF8_1_BYTE_MAX -> 1
            codePoint <= UTF8_2_BYTE_MAX -> 2
            codePoint <= UTF8_3_BYTE_MAX -> UTF8_3_BYTES
            else -> UTF8_4_BYTES
        }

    /**
     * AD-230（2026-09-26 审计）：Content-Disposition 文件名解析——此前只认
     * 小写字面 `filename=`：RFC 5987 `filename*=UTF-8''…`（非 ASCII 文件名的
     * 标准形态）与大小写变体（`FileName=`）全部漏解析。优先 filename*
     * （剥 charset 前缀后百分号解码），回退 filename（大小写不敏感）；
     * 均未命中返回空串（交由后续 URL/默认名兜底）。
     *
     * AD-263（2026-10-01 审计）：①token 边界锚定——`(?:^|[;\\s])` 前置边界，
     * `xfilename=` 不再误匹配；②RFC 5987 解码不走 URLDecoder（其把 `+` 按
     * query 语义解成空格，filename* 里 `+` 是字面加号）——逐 %XX 严格解码
     * （[decodePercentStrict]）。
     */
    internal fun resolveDispositionFileName(contentDisposition: String): String {
        val starred =
            Regex("(?:^|[;\\s])filename\\*=([^;]+)", RegexOption.IGNORE_CASE)
                .find(contentDisposition)
                ?.groupValues
                ?.get(1)
                ?.trim()
        if (!starred.isNullOrBlank()) {
            // RFC 5987 形如 `UTF-8''%E6%8A%A5.pdf`——剥 charset'' 前缀后解码；
            // 无前缀（裸百分号编码）按原串处理
            val encoded = starred.substringAfter("''", missingDelimiterValue = starred)
            return decodePercentStrict(encoded)
        }
        return Regex("(?:^|[;\\s])filename=([^;]+)", RegexOption.IGNORE_CASE)
            .find(contentDisposition)
            ?.groupValues
            ?.get(1)
            ?.trim(' ', '"', ';')
            .orEmpty()
    }

    /**
     * AD-263：RFC 5987 严格百分号解码——逐 %XX 还原字节流后整体按 UTF-8 解码
     * （多字节字符的 %E6%8A%A5 序列不得按单字节劈开）；`+` 保持字面（不经
     * URLDecoder 的 query 语义转换）；%XX 后不足两位十六进制按字面 `%` 处理；
     * 解码出非法 UTF-8 序列原样返回（fail-closed）。AD-305：URL 路径段解码
     * 自本函数单源（原 decodePercent 的 query 语义已随 AD-305 移除）。
     */
    private fun decodePercentStrict(raw: String): String {
        // 字面字符按 UTF-8 展开最多 4 字节/字符——按上界分配
        val bytes = ByteArray(raw.length * UTF8_4_BYTES)
        var length = 0
        var i = 0
        while (i < raw.length) {
            val escapedByte = hexEscapeByteAt(raw, i)
            if (escapedByte != null) {
                bytes[length++] = escapedByte
                i += PERCENT_ESCAPE_LENGTH
            } else {
                val literal = raw[i].toString().toByteArray(Charsets.UTF_8)
                literal.forEach { bytes[length++] = it }
                i++
            }
        }
        return try {
            Charsets.UTF_8
                .newDecoder()
                .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(bytes, 0, length))
                .toString()
        } catch (_: java.nio.charset.CharacterCodingException) {
            raw
        }
    }

    /** AD-263：位置 [index] 起的 `%XX` 转义字节；非完整十六进制转义返回 null。 */
    private fun hexEscapeByteAt(
        raw: String,
        index: Int,
    ): Byte? {
        val high = hexValue(raw.getOrNull(index + 1))
        val low = hexValue(raw.getOrNull(index + 2))
        return if (raw[index] == '%' && high != null && low != null) {
            ((high shl HEX_NIBBLE_SHIFT) or low).toByte()
        } else {
            null
        }
    }

    /** AD-263：单字符十六进制值；非十六进制返回 null。 */
    private fun hexValue(c: Char?): Int? =
        if (c == null) {
            null
        } else {
            when (c) {
                in '0'..'9' -> c - '0'
                in 'a'..'f' -> c - 'a' + HEX_RADIX_OFFSET
                in 'A'..'F' -> c - 'A' + HEX_RADIX_OFFSET
                else -> null
            }
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

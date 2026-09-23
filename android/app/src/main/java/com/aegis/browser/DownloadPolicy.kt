package com.aegis.browser

import java.net.URLDecoder

object DownloadPolicy {
    private val dangerousExtensions =
        setOf(
            "exe",
            "bat",
            "cmd",
            "com",
            "msi",
            "scr",
            "pif",
            "vbs",
            "vbe",
            "js",
            "jse",
            "wsf",
            "wsh",
            "ps1",
            "psm1",
            "lnk",
            "hta",
            "jar",
            "apk",
            "dll",
            "reg",
            "cpl",
            "appref-ms",
        )

    /**
     * 危险扩展判定（P2-5 修复 + AD-002 补强）：候选集 =
     * 净化后下载文件名 ∪ URL 路径末段 ∪ 查询参数值末段（解码后），判定前
     * 去控制字符/尾点 + 小写化。历次修复：
     * - 原实现仅看 [Uri.getLastPathSegment]——对 `/download?file=x.exe`
     *   与 `x.exe.` 漏判（P2-5）；
     * - AD-002（2026-09-23 审计）：查询串此前被整体排除——
     *   `https://evil.com/dl?file=x.exe`（路径无扩展、真实名在查询参数）
     *   完整绕过；Windows 侧 P79 同类缺口。现补查询参数值逐个解码后取
     *   尾段参与判定（与 Windows ExtractExtension/Unescape 口径对齐）。
     *
     * 实现为纯字符串+URLDecoder——不依赖 android.net.Uri，JVM 单测可直测。
     *
     * @param url      下载直链
     * @param fileName WebViewDownloadHandler 解析并净化后的下载文件名（可空）
     */
    fun requiresExplicitConfirmation(
        url: String,
        fileName: String = "",
    ): Boolean {
        val withoutFragment = url.substringBefore('#')
        val pathSegment = withoutFragment.substringBefore('?').substringAfterLast('/')
        val queryValues =
            withoutFragment
                .substringAfter('?', missingDelimiterValue = "")
                .split('&')
                .mapNotNull { entry ->
                    // 取 '=' 后的参数值；无值条目（裸 flag 参数）不参与判定
                    if ('=' in entry) entry.substringAfter('=') else null
                }.filter { it.isNotEmpty() }
                .map(::decodeQueryValue)
                .map { it.substringAfterLast('/') }
        val candidates = sequenceOf(fileName, pathSegment) + queryValues.asSequence()
        return candidates
            .mapNotNull(::normalizeCandidate)
            .map { it.substringAfterLast('.', missingDelimiterValue = "") }
            .any { it in dangerousExtensions }
    }

    /** 查询参数值百分号解码；非法编码原样返回（fail-closed——仍参与判定）。 */
    private fun decodeQueryValue(raw: String): String =
        try {
            URLDecoder.decode(raw, Charsets.UTF_8)
        } catch (_: IllegalArgumentException) {
            raw
        }

    /**
     * P2-5 修复：判定前净化——去控制字符与首尾空白、去尾点（`x.exe.` →
     * `x.exe`）、小写化；`..` 段净化后为空不参与判定；空结果返回 null。
     */
    private fun normalizeCandidate(raw: String): String? =
        raw
            .filterNot { it.isISOControl() }
            .trim()
            .trimEnd('.')
            .takeIf { it.isNotBlank() }
            ?.lowercase()
}

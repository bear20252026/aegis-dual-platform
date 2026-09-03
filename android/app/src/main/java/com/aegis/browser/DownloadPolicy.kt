package com.aegis.browser

import android.net.Uri

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
     * 危险扩展判定（P2-5 修复（全面审计 2026-09-04））：候选集 =
     * 净化后下载文件名 ∪ URL 去掉查询串后的路径段，判定前去控制字符/
     * 尾点 + 小写化。原实现仅看 [Uri.getLastPathSegment]——对
     * `/download?file=x.exe`（真实文件名在 Content-Disposition）与
     * `x.exe.`（尾点使 substringAfterLast('.') 取空）漏判。
     *
     * @param url      下载直链
     * @param fileName WebViewDownloadHandler 解析并净化后的下载文件名（可空）
     */
    fun requiresExplicitConfirmation(
        url: String,
        fileName: String = "",
    ): Boolean {
        val uri = Uri.parse(url)
        val urlPathSegment = uri.path.orEmpty().substringAfterLast('/')
        val extensions =
            listOf(fileName, urlPathSegment)
                .mapNotNull(::normalizeCandidate)
                .map { it.substringAfterLast('.', missingDelimiterValue = "") }
        return extensions.any { it in dangerousExtensions }
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

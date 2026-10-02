package com.aegis.browser

import java.net.URLDecoder

object DownloadPolicy {
    // AD-306（2026-10-02 审计）：危险扩展名集与 Windows 失衡补齐——口径：
    // ①Android 无执行意义可豁免（如 bat/cmd 在 Android 不经 shell 执行，但
    //   下载文件常经云盘/USB 迁移到 PC，跨端可迁移危险不可豁免）；
    // ②跨端可迁移危险项补入：iso/vhd（镜像挂载）、py/pyw（脚本）、jnlp
    //   （Java Web Start）、url/website（IE 快捷方式）、chm（编译帮助，
    //   内嵌脚本执行面）、scf（Shell Command File——资源管理器命令执行）。
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
            // AD-306（2026-10-02 审计）：跨端可迁移危险项
            "iso",
            "vhd",
            "py",
            "pyw",
            "jnlp",
            "url",
            "website",
            "chm",
            "scf",
        )

    /**
     * 一级判定（AD-331，2026-10-02 审计）：路径/文件名命中危险扩展 → 硬拦截。
     * 候选集 = 净化后下载文件名 ∪ URL 路径末段（解码后）——命中即无条件
     * 拦截（不提供确认豁免：文件本体即危险载荷）。
     *
     * @param url      下载直链
     * @param fileName WebViewDownloadHandler 解析并净化后的下载文件名（可空）
     */
    fun isHardBlocked(
        url: String,
        fileName: String = "",
    ): Boolean = hitDangerousExtension(sequenceOf(fileName, pathSegmentOf(url)))

    /**
     * 二级判定（AD-331，2026-10-02 审计）：仅查询参数命中危险扩展 → 需经
     * MainDialogs 单槽显式确认后允许继续（名实相符的原
     * requiresExplicitConfirmation 语义——此前承诺确认、实现硬拦截）。
     * 历史口径：
     * - P2-5：原实现仅看 [android.net.Uri.getLastPathSegment]——对
     *   `/download?file=x.exe` 与 `x.exe.` 漏判；
     * - AD-002（2026-09-23 审计）：查询参数值逐个解码后取尾段参与判定
     *   （与 Windows ExtractExtension/Unescape 口径对齐）。
     */
    fun requiresExplicitConfirmation(
        url: String,
        fileName: String = "",
    ): Boolean {
        if (isHardBlocked(url, fileName)) return false // 一级已硬拦截——二级不再重复判定
        return hitDangerousExtension(queryValueSegmentsOf(url))
    }

    /**
     * 危险扩展判定（P2-5 修复 + AD-002 补强——AD-331 拆两级后的共享内核）：
     * 候选净化（去控制字符/尾点 + 小写化）后取末段扩展名查危险集。
     * 实现为纯字符串+URLDecoder——不依赖 android.net.Uri，JVM 单测可直测。
     */
    private fun hitDangerousExtension(candidates: Sequence<String>): Boolean =
        candidates
            .mapNotNull(::normalizeCandidate)
            .map { it.substringAfterLast('.', missingDelimiterValue = "") }
            .any { it in dangerousExtensions }

    /** AD-331：URL 路径末段候选（fragment/query 剥离 + 百分号解码后取尾段）。 */
    private fun pathSegmentOf(url: String): String =
        // AD-217（2026-09-26 审计）：路径段先百分号解码再取尾段——AD-002 只给
        // 查询值补了解码，`/dl/malware%2Eexe` 路径段归一后无字面 `.`，危险
        // 扩展漏判（与 Windows 侧 Unescape 口径对齐）。
        decodeQueryValue(url.substringBefore('#').substringBefore('?'))
            .substringAfterLast('/')

    /** AD-331：查询参数值末段候选（逐值解码后取尾段）。 */
    private fun queryValueSegmentsOf(url: String): Sequence<String> =
        url
            .substringBefore('#')
            .substringAfter('?', missingDelimiterValue = "")
            .split('&')
            .asSequence()
            .mapNotNull { entry ->
                // 取 '=' 后的参数值；无值条目（裸 flag 参数）不参与判定
                if ('=' in entry) entry.substringAfter('=') else null
            }.filter { it.isNotEmpty() }
            .map(::decodeQueryValue)
            .map { it.substringAfterLast('/') }

    /**
     * 查询参数值百分号解码；非法编码原样返回（fail-closed——仍参与判定）。
     * AD-066 lint 门禁修复：Charset 重载是 API 33+（minSdk 26 会 NewApi 崩溃）
     * ——改用 API 1 就有的 String charset 名重载（语义一致）。
     */
    private fun decodeQueryValue(raw: String): String =
        try {
            URLDecoder.decode(raw, "UTF-8")
        } catch (_: IllegalArgumentException) {
            raw
        } catch (_: java.io.UnsupportedEncodingException) {
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

package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * WebViewDownloadHandler 文件名链 JVM 单测（2026-09-24 审计——AD-026/027）。
 * 纯字符串实现（AD-027 重构）——URL 路径段提取不依赖 android.net.Uri。
 */
class WebViewDownloadHandlerTest {
    // ------------------------------------------------ AD-026 sanitizeFileName
    @Test
    fun sanitizeStripsPathSeparators() {
        assertEquals("passwd", WebViewDownloadHandler.sanitizeFileName("/etc/passwd"))
        assertEquals("evil.exe", WebViewDownloadHandler.sanitizeFileName("..\\evil.exe"))
        assertEquals("evil.exe", WebViewDownloadHandler.sanitizeFileName("a/b/evil.exe"))
    }

    @Test
    fun sanitizeRemovesControlCharsAndTrims() {
        assertEquals("ab", WebViewDownloadHandler.sanitizeFileName("a\u0000b"))
        assertEquals("ab", WebViewDownloadHandler.sanitizeFileName("a\u0007b"))
        assertEquals("x.exe", WebViewDownloadHandler.sanitizeFileName("  x.exe  "))
        assertEquals("x.exe", WebViewDownloadHandler.sanitizeFileName("x.exe."))
        assertEquals("x.exe", WebViewDownloadHandler.sanitizeFileName("x.exe..."))
    }

    @Test
    fun sanitizeRejectsBlankAndDotOnlyNames() {
        assertNull(WebViewDownloadHandler.sanitizeFileName(""))
        assertNull(WebViewDownloadHandler.sanitizeFileName("..."))
        assertNull(WebViewDownloadHandler.sanitizeFileName("../.."))
        assertNull(WebViewDownloadHandler.sanitizeFileName("///"))
    }

    // ---------------------------------------- AD-027 resolveDownloadFileName
    @Test
    fun dispositionFilenameHasTopPriority() {
        assertEquals(
            "report.pdf",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/path/file.zip",
                "application/octet-stream",
                "attachment; filename=\"report.pdf\"",
            ),
        )
    }

    @Test
    fun urlPathSegmentIsSecondPriority() {
        assertEquals(
            "photo.jpg",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/dir/photo.jpg", "", ""),
        )
        // query 不参与 URL 路径段（纯字符串剥离——与 Uri.getLastPathSegment 语义一致）
        assertEquals(
            "get",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/get?file=x.exe", "", ""),
        )
    }

    @Test
    fun defaultNameWithMimeInferredExtension() {
        assertEquals(
            "aegis_download.pdf",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/", "application/pdf", ""),
        )
        // 推断不出扩展名 → 保持默认名不加后缀
        assertEquals(
            "aegis_download",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/", "", ""),
        )
    }

    @Test
    fun traversalAndControlCharsInDispositionAreNeutralized() {
        assertEquals(
            "evil.exe",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"../../etc/evil.exe\"",
            ),
        )
        assertEquals(
            "name.exe",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"na\u0000me.exe\"",
            ),
        )
    }

    @Test
    fun combinedNameIsSanitizedAgainAfterInference() {
        // 推断出的扩展名组合进 base 后再净化一次（净化兜底不随白名单化失效）
        assertEquals(
            "base.txt",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/base", "text/plain", ""),
        )
    }

    // ---------------- AD-131/138（审计 2026-09-23 清单·A6 批） ----------------

    @Test
    fun mimeExtensionUsesWhitelistMapping() {
        // AD-138：mimetype → 扩展名走精确白名单（大小写/空白归一）
        assertEquals(
            "aegis_download.pdf",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/", "application/pdf", ""),
        )
        assertEquals(
            "aegis_download.txt",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/", "TEXT/PLAIN ", ""),
        )
        assertEquals(
            "base.xlsx",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/base",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "",
            ),
        )
    }

    @Test
    fun unknownMimeSubtypeIsNoLongerUsedAsExtension() {
        // AD-138：原实现把 mime 子类型直接当扩展名（x-msdownload /
        // octet-stream 等无意义后缀）——白名单化后未命中回落 URL 段，
        // 再推不出不加后缀
        assertEquals(
            "aegis_download",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/", "application/x-msdownload", ""),
        )
        assertEquals(
            "getfile",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/getfile", "application/octet-stream", ""),
        )
        // base 已带扩展名时不触发 mime 推断
        assertEquals(
            "setup.bin",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/setup.bin", "application/octet-stream", ""),
        )
    }

    @Test
    fun urlPathSegmentExtensionWinsWhenMimeUnknown() {
        // AD-131：inferExtension 独立路径——mime 推不出时回落 URL 路径段扩展
        assertEquals(
            "report.pdf",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/files/report.pdf", "", ""),
        )
        // URL 段也无扩展、无 mime → URL 路径段兜底名（非默认名——路径段在
        // 文件名解析链中先于 DEFAULT_DOWNLOAD_NAME）
        assertEquals(
            "getfile",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/getfile?token=x", "", ""),
        )
    }

    // ------------------------------------------------ AD-032 长度上限
    @Test
    fun overLongFileNameIsCappedTo200KeepingExtension() {
        val longName = "a".repeat(250) + ".pdf"
        val resolved =
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"$longName\"",
            )
        assertEquals(200, resolved.length)
        assertTrue("扩展名必须保留（不得截成无类型文件）", resolved.endsWith(".pdf"))
        assertTrue(resolved.startsWith("a"))
    }

    @Test
    fun overLongExtensionlessNameIsCapped() {
        val resolved =
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"${"b".repeat(300)}\"",
            )
        assertEquals(200, resolved.length)
    }

    @Test
    fun normalLengthNamesPassThroughUncapped() {
        assertEquals(
            "report.pdf",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"report.pdf\"",
            ),
        )
    }

    // ---------------- AD-230（2026-09-26 审计）：RFC 5987 filename* 与大小写变体 ----------------

    @Test
    fun rfc5987StarFilenameTakesPriorityAndDecodes() {
        // filename*=UTF-8''…（非 ASCII 文件名的标准形态）此前完全不解析
        assertEquals(
            "报告.pdf",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"fallback.bin\"; filename*=UTF-8''%E6%8A%A5%E5%91%8A.pdf",
            ),
        )
        assertEquals(
            "my file.txt",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename*=UTF-8''my%20file.txt",
            ),
        )
    }

    @Test
    fun dispositionFilenameMatchingIsCaseInsensitive() {
        // FileName=/FILENAME= 变体此前漏解析（只认小写字面 filename=）
        assertEquals(
            "report.pdf",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; FileName=\"report.pdf\"",
            ),
        )
        assertEquals(
            "report.pdf",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; FILENAME=\"report.pdf\"",
            ),
        )
    }

    @Test
    fun percentEncodedPathSegmentDecodesToFileName() {
        // AD-217 配套：URL 路径段此前不解码——malware%2Eexe 拿不到扩展名
        assertEquals(
            "malware.exe",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/dl/malware%2Eexe", "", ""),
        )
    }
}

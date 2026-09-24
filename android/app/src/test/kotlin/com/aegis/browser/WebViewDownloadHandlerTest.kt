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
        // 推断出的扩展名可能携带分隔符——组合名兜底再净化
        assertEquals(
            "base.exe",
            WebViewDownloadHandler.resolveDownloadFileName("https://c.d/base", "application/x\\exe", ""),
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
}

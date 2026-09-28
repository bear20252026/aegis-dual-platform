package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * DownloadPolicy 离线单测（2026-09-23 审计——AD-002/AD-024/AD-025）。
 * 纯 JVM：DownloadPolicy 已不依赖 android.net.Uri。
 */
class DownloadPolicyTest {
    // AD-025：危险扩展全集矩阵——增删条目必须有测试感知
    @Test
    fun dangerousExtensionMatrix_allKnownDangerous() {
        val all =
            listOf(
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
        for (ext in all) {
            assertTrue(
                "扩展 .$ext 应判危险",
                DownloadPolicy.requiresExplicitConfirmation("https://c.d/file.$ext"),
            )
        }
    }

    @Test
    fun benignExtensionsPass() {
        for (ext in listOf("jpg", "png", "pdf", "zip", "html")) {
            assertFalse(DownloadPolicy.requiresExplicitConfirmation("https://c.d/file.$ext"))
        }
    }

    // AD-002：查询参数携带危险扩展——此前完整绕过
    @Test
    fun queryParameterCarryingDangerousExtension_detected() {
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://evil.com/dl?file=x.exe"))
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://evil.com/dl?p=1&name=mal.bat"))
    }

    @Test
    fun percentEncodedQueryValue_detected() {
        // f=x%2Fy.exe 解码后路径段 y.exe
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://c.d/dl?f=x%2Fy.exe"))
    }

    // AD-217（2026-09-26 审计）：URL 路径段此前不参与百分号解码——
    // `/dl/malware%2Eexe` 归一后无字面 `.`，危险扩展漏判
    @Test
    fun percentEncodedPathSegment_detected() {
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://evil.com/dl/malware%2Eexe"))
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://evil.com/dl/malware%2eexe"))
        // 编码分隔符形态：dl%2Fmalware.exe 解码后取尾段
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://evil.com/dl%2Fmalware.exe"))
    }

    @Test
    fun malformedPercentEncoding_fallsBackToRaw() {
        // 非法编码（孤立 %）不抛——原样参与判定仍命中
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://c.d/dl?f=x%.exe"))
    }

    // AD-024：P2-5 净化回归——大写与尾点
    @Test
    fun uppercaseAndTrailingDot_detected() {
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://c.d/X.EXE"))
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://c.d/x.exe."))
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://c.d/ok.png", fileName = "X.EXE"))
    }

    @Test
    fun plainPageUrl_clean() {
        assertFalse(DownloadPolicy.requiresExplicitConfirmation("https://example.com/article?id=42"))
        assertFalse(DownloadPolicy.requiresExplicitConfirmation("https://example.com/", fileName = "report.pdf"))
    }

    @Test
    fun emptyUrlAndName_false() {
        assertFalse(DownloadPolicy.requiresExplicitConfirmation("", ""))
    }

    @Test
    fun fileNameDangerousEvenWhenUrlClean() {
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://example.com/get", fileName = "setup.msi"))
    }
}

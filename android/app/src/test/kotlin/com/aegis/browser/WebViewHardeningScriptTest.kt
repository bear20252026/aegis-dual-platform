package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * AD-005（审计 2026-09-23 清单·真机批次）：fingerprint-shield 脚本结构锚点。
 * per-site 种子派生已从自制 acc*31 混合迁移为内嵌同步 SHA-256——构造与
 * Rust per_site_seed（RS-025/P25）对齐：
 *   SHA-256(hexDecode(sessionSeed) || 'aegis:per-site-seed:v2:' || domain)[0..16] hex。
 * 迁移背景：document-start 一次性注入架构（addDocumentStartJavaScript 无
 * per-page 入口）决定派生必须留在 JS 侧，故台账「Kotlin 侧派生」在此约束下
 * 落地为「JS 内嵌同步 SHA-256、构造对齐 Rust」。
 * 已知答案验证在模拟器 instrumented 冒烟
 * （SmokeInstrumentedTest.perSiteSeedSha256KnownAnswerOnDevice，真 Chromium
 * 执行对 Kotlin MessageDigest 逐字节比对）；此处锁定迁移不回退的结构事实。
 */
class WebViewHardeningScriptTest {
    private val script =
        WebViewHardening.fingerprintShieldScript(
            "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
        )

    @Test
    fun seedDerivationUsesSha256Construction() {
        assertTrue("缺少 Rust 对齐的分隔常量", script.contains("aegis:per-site-seed:v2:"))
        assertTrue("缺少内嵌 SHA-256 实现", script.contains("function sha256Raw"))
        assertTrue("缺少 deriveSeed 入口", script.contains("function deriveSeed"))
    }

    @Test
    fun homemadeAcc31HashIsGone() {
        assertFalse("自制 acc*31 混合仍在脚本中（AD-005 迁移回退）", script.contains("Math.imul(acc, 31)"))
    }
}

package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * WebViewHardening 会话种子 JVM 单测（2026-09-24 审计——AD-023）。
 * newSessionSeed 是指纹防护的熵源——熵退化 = 每会话指纹噪声恒定 = 伪装失效。
 */
class WebViewHardeningTest {
    @Test
    fun sessionSeedIs64HexChars() {
        val seed = WebViewHardening.newSessionSeed()
        assertEquals(64, seed.length)
        assertTrue("种子必须是十六进制小写", seed.all { it in "0123456789abcdef" })
    }

    @Test
    fun sessionSeedsAreUniqueAcrossCalls() {
        val seeds = (1..32).map { WebViewHardening.newSessionSeed() }.toSet()
        assertEquals("32 次种子必须两两不同（熵源不得退化）", 32, seeds.size)
    }

    @Test
    fun consecutiveSeedsDiffer() {
        // 恒等退化（如错误地复用固定数组）会在此立即暴露
        assertNotEquals(WebViewHardening.newSessionSeed(), WebViewHardening.newSessionSeed())
    }

    // ---------------- AD-069（2026-09-24 审计）：BRIDGE_GUARD_JS 防御标记回归 ----------------

    @Test
    fun bridgeGuardScriptContainsAllDefenseMarkers() {
        val js = WebViewHardening.BRIDGE_GUARD_JS
        val markers =
            listOf(
                "window.fetch",
                "XMLHttpRequest",
                "sendBeacon",
                "window.WebSocket",
                "shouldBlock",
                "trustedCaller",
                "[Aegis] Bridge blocked",
            )
        for (marker in markers) {
            assertTrue("BRIDGE_GUARD_JS 缺少防御标记: $marker", js.contains(marker))
        }
    }

    @Test
    fun bridgeGuardScriptKeepsWhitelistAndHttpsRequirement() {
        val js = WebViewHardening.BRIDGE_GUARD_JS
        // 白名单单源（与 ALLOWED_BRIDGE_HOSTS 一致）
        assertTrue(js.contains("aegis.local"))
        assertTrue(js.contains("localhost"))
        assertTrue(js.contains("127.0.0.1"))
        // bridge 目标强制 HTTPS（生产接线已开启）
        assertTrue("REQUIRE_HTTPS 必须保持 true", js.contains("REQUIRE_HTTPS = true"))
    }
}

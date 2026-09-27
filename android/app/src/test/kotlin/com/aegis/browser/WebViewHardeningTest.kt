package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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

    // ---------------- AD-247（2026-09-26 审计）：fingerprintShieldScript 9 阶段标记回归 ----------------

    /** 测试种子（64 位 hex——与 newSessionSeed 同形态，确定性注入）。 */
    private val testSeed = "00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff"

    @Test
    fun fingerprintShieldScriptContainsAllStageMarkers() {
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        val markers =
            listOf(
                "window.__AEGIS_PROTECTION_VERSION", // 阶段标记：版本
                "Function.prototype.toString", // Stage 1：ToStringGuard
                "__AEGIS_SITE_SEED", // Stage 2：PerSiteSeed
                "HTMLCanvasElement.prototype.toDataURL", // Stage 3：Canvas 噪声
                "WebGLRenderingContext.prototype.getParameter", // Stage 3b：WebGL 参数
                "hardwareConcurrency", // Stage 3c：硬件并发伪装
                "Screen.prototype", // Stage 4：LetterboxShield
                "'__hsfp'", // Stage 5：QueryStripper
                "FontFaceSet.prototype.check", // Stage 6：FontNormalizer
                "0x9245", // Stage 7：WebGLSpoof
                "performance.now", // Stage 8：TimerPrecision
                "clients2\\.google\\.com", // Stage 9：ExtProxy
            )
        for (marker in markers) {
            assertTrue("fingerprintShieldScript 缺少阶段标记: $marker", js.contains(marker))
        }
        // 会话种子必须注入脚本（Stage 2 派生 per-site seed 的熵源）
        assertTrue(js.contains(testSeed))
    }

    @Test
    fun canvasNoiseUsesOffscreenCopyNotLiveCanvas() {
        // AD-212（2026-09-26 审计）回归：噪声必须施加在离屏副本——活画布上的
        // 破坏性读改写使二次读取可检测且页面后续渲染被永久污染
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        assertTrue("必须创建离屏副本", js.contains("document.createElement('canvas')"))
        assertTrue("副本必须经 drawImage 取源", js.contains("drawImage(this, 0, 0)"))
        assertTrue("噪声写回副本上下文", js.contains("octx.putImageData(imageData, 0, 0)"))
        assertTrue("返回值取自副本", js.contains("origToDataURL.apply(off, arguments)"))
        assertFalse("不得直读源画布像素尺寸（破坏性读改写检测面）", js.contains("this.width, this.height"))
        assertFalse("不得取源画布 2d 上下文（无上下文画布被永久锁定 2d）", js.contains("this.getContext"))
    }

    // ---------------- AD-107/108（审计 2026-09-23 清单·A6 批） ----------------

    @Test
    fun etld1DerivationUsesMiniPublicSuffixList() {
        // AD-107：getETLD1 一律取最后两段对共享公共后缀（co.uk 等）推导出
        // 错误的 per-site seed——必须内嵌迷你 PSL 并对命中后缀取三段
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        assertTrue("必须内嵌迷你公共后缀表", js.contains("PUBLIC_SUFFIXES"))
        assertTrue("须覆盖最高频共享后缀 co.uk", js.contains("'co.uk'"))
        assertTrue("须覆盖 com.cn", js.contains("'com.cn'"))
        assertTrue("公共后缀命中须取三段推导 eTLD+1", js.contains("p.slice(-3).join('.')"))
    }

    @Test
    fun dateNowJitterIsIntegralOnly() {
        // AD-108：随机抖动只进 performance.now——Date.now 返回非整数毫秒
        // 本身是高置信检测信号，且破坏页内整毫秒假设
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        assertTrue(
            "Date.now 必须走整数取整路径（无随机分量）",
            js.contains("Date.now = function() { return reduceIntegral(d()); }"),
        )
        assertFalse("Date.now 不得叠加随机抖动", js.contains("return reduce(d());"))
    }
}

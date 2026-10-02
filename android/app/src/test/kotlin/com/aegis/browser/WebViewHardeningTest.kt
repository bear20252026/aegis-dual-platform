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

    @Test
    fun bridgeGuardScriptKeepsWebSocketPrototypeAlignment() {
        // AD-105（审计 2026-09-23 清单·A6 批）：WebSocket 包装必须对齐真实现
        // 原型——否则 new WebSocket(...) instanceof WebSocket 恒 false（页面
        // 一行即可探测防护存在性）。
        val js = WebViewHardening.BRIDGE_GUARD_JS
        assertTrue(
            "WebSocket 包装必须对齐 WS.prototype（instanceof 语义保持）",
            js.contains("window.WebSocket.prototype = WS.prototype"),
        )
        // 静态常量四态必须随包装保留
        listOf("CONNECTING", "OPEN", "CLOSING", "CLOSED").forEach { state ->
            assertTrue("WebSocket.$state 常量缺失", js.contains("window.WebSocket.$state"))
        }
    }

    // ---------------- AD-247（2026-09-26 审计）：fingerprintShieldScript 9 阶段标记回归 ----------------

    /** 测试种子（64 位 hex——与 newSessionSeed 同形态，确定性注入）。 */
    private val testSeed = "00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff"

    @Test
    fun fingerprintShieldScriptContainsAllStageMarkers() {
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        val markers =
            listOf(
                // AD-269（2026-10-01 审计）：版本标记改 defineProperty 注入
                // （不可枚举/不可配置）——标记锚定属性名字面量
                "__AEGIS_PROTECTION_VERSION",
                "Function.prototype.toString", // Stage 1：ToStringGuard
                "__AEGIS_SITE_SEED", // Stage 2：PerSiteSeed
                "HTMLCanvasElement.prototype.toDataURL", // Stage 3：Canvas 噪声
                "hardwareConcurrency", // Stage 3c：硬件并发伪装
                "Screen.prototype", // Stage 4：LetterboxShield
                "'__hsfp'", // Stage 5：QueryStripper
                "FontFaceSet.prototype.check", // Stage 6：FontNormalizer
                "0x9245", // Stage 7：WebGLSpoof（AD-258 后唯一 getParameter 伪装源）
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
        // AD-298 后 convertToBlob 通道以 new OffscreenCanvas(this.width, this.height)
        // 取副本尺寸（合法）——破坏性形态只锁「按源画布尺寸直读源像素」。
        assertFalse(
            "不得按源画布尺寸直读源像素（破坏性读改写检测面）",
            js.contains("getImageData(0, 0, this.width, this.height)"),
        )
        assertFalse("不得取源画布 2d 上下文（无上下文画布被永久锁定 2d）", js.contains("this.getContext"))
    }

    // ---------------- AD-175/176（审计 2026-09-23 清单·A7 批） ----------------

    @Test
    fun canvasNoisePerturbsAllRgbChannels() {
        // AD-175：原噪声只扰动 R 通道——G/B 逐像素原样返回，2/3 的读回信息
        // 未覆盖（通道差分即可高置信还原）。三通道必须各有独立抖动写入。
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        // AD-311 起噪声写回为 aegisNudge 离岸形态（0/255 clamp 吸收面修复）
        assertTrue("R 通道抖动缺失", js.contains("imageData.data[i] = aegisNudge("))
        assertTrue("G 通道抖动缺失（仅 R 通道混淆不充分）", js.contains("imageData.data[i + 1] = aegisNudge("))
        assertTrue("B 通道抖动缺失（仅 R 通道混淆不充分）", js.contains("imageData.data[i + 2] = aegisNudge("))
    }

    @Test
    fun letterboxGridConstantsStayDocumented() {
        // AD-176：尺寸量化网格常量（WS/HS）必须保持注释固化的设计约束
        // （跨属性/跨站点一致网格——变更为逐会话随机即引入可探测的分叉）
        val js = WebViewHardening.fingerprintShieldScript(testSeed)
        assertTrue("Letterbox 网格常量缺失", js.contains("var WS = 200, HS = 100;"))
        assertTrue(
            "网格步长必须保持设计约束注释（AD-176 固化理由）",
            js.contains("尺寸量化网格步长"),
        )
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
        // AD-314 起包装先落具名变量再挂载（ToStringGuard 注册需要引用）——断言
        // 对齐实际挂载形态；整数取整（无随机分量）语义不变。
        assertTrue(
            "Date.now 必须走整数取整路径（无随机分量）",
            js.contains("var dateWrapper = function() { return reduceIntegral(d()); };"),
        )
        assertFalse("Date.now 不得叠加随机抖动", js.contains("return reduce(d());"))
    }
}

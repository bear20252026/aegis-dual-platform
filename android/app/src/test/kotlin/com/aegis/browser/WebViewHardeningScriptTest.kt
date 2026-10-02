package com.aegis.browser

import org.junit.Assert.assertEquals
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
 *
 * AD-272（2026-10-01 审计）：9 阶段脚本此前仅 Stage 2 三条断言——逐阶段
 * 补关键标记断言（任一阶段被误删/误改而注入照常的零回归盲区在此失败）。
 */
class WebViewHardeningScriptTest {
    private val script =
        WebViewHardening.fingerprintShieldScript(
            "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
        )

    // ------------------------------------------------------------- Stage 1

    @Test
    fun stage1ToStringGuardRegistersProxyMap() {
        assertTrue("Stage 1 缺少 ToStringGuard 劫持点", script.contains("Function.prototype.toString"))
        assertTrue("Stage 1 缺少代理注册出口", script.contains("__AEGIS_REGISTER_PROXY"))
        assertTrue("Stage 1 缺少 proxyMap 归一查表", script.contains("proxyMap.has(this)"))
    }

    // ------------------------------------------------------------- Stage 2

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

    // ------------------------------------------------------------- Stage 3

    @Test
    fun stage3CanvasNoiseUsesPerPixelPrng() {
        // AD-253：逐像素确定性 PRNG——像素索引乘黄金比例常数与 seed 异或取 LSB；
        // 退化形态 `(seed + i) % 2`（i+=4 步进下每通道全图常量偏移）必须不存在
        assertTrue("Stage 3 缺少逐像素 imul 混合", script.contains("Math.imul(px, 0x9E3779B1)"))
        assertTrue("Stage 3 缺少三通道混合常数（G 通道）", script.contains("Math.imul(px, 0x85EBCA6B)"))
        assertTrue("Stage 3 缺少三通道混合常数（B 通道）", script.contains("Math.imul(px, 0x27D4EB2F)"))
        assertFalse("退化常量偏移噪声 `(seed + i)` 仍在（AD-253 回退）", script.contains("(seed + i)"))
    }

    @Test
    fun stage3ToDataURLHasSizeCap() {
        // AD-270：超尺寸画布直接走原实现（资源放大防护）
        assertTrue("Stage 3 缺少尺寸上限常量", script.contains("MAX_NOISE_PIXELS"))
        assertTrue("Stage 3 缺少超限降级分支", script.contains("origToDataURL.apply(this, arguments)"))
    }

    @Test
    fun stage3DeadWebglGetParameterWrapperIsGone() {
        // AD-258：Stage 3 的 getParameter 伪装被 Stage 7 先行返回（永不可达）
        // ——'Aegis Privacy' 是现成指纹标记，必须整体移除
        assertFalse("Stage 3 死代码 'Aegis Privacy' 仍在（AD-258 回退）", script.contains("Aegis Privacy"))
        assertFalse("Stage 3 死代码 'ANGLE (Aegis)' 仍在（AD-258 回退）", script.contains("ANGLE (Aegis)"))
        // WebGL vendor/renderer 伪装单源收敛 Stage 7（0x9245/0x9246）
        assertTrue("Stage 7 WebGL 伪装必须保留", script.contains("0x9245"))
    }

    /**
     * AD-253：JS 侧噪声公式的 Kotlin 镜像（同口径验证，非生产逻辑）——
     * `((seed ^ Math.imul(px, C)) >>> 0) & 1 ? 1 : -1`。Kotlin Int 乘法与
     * xor 语义同 32 位环绕（>>> 0 后 & 1 等价于直接取 LSB）。
     */
    private fun noiseTriple(
        seed: Int,
        px: Int,
    ): Triple<Int, Int, Int> {
        fun sign(channelConstant: Int): Int = if (((seed xor (px * channelConstant)) and 1) == 1) 1 else -1
        return Triple(sign(0x9E3779B1.toInt()), sign(0x85EBCA6B.toInt()), sign(0x27D4EB2F.toInt()))
    }

    @Test
    fun canvasNoiseIsNotConstantPerChannelForAnySeed() {
        // 旧退化形态：i+=4 步进下 (seed+i)%2 每通道全图恒定（共 8 种组合，
        // 减法即可还原原图）。逐像素 PRNG 后：任一 seed 的 64×64 画布上
        // 每通道必须同时出现 +1 与 -1（噪声非常量偏移）。
        val seeds = listOf(0, 1, -1, Int.MIN_VALUE + 5, Int.MAX_VALUE, 0x2F9E1B3C.toInt(), 0x51ED270B.toInt())
        for (seed in seeds) {
            val channelValues =
                List(3) { channel ->
                    (0 until 64 * 64).map { px -> noiseTriple(seed, px).toList()[channel] }.toSet()
                }
            channelValues.forEachIndexed { channel, values ->
                assertEquals("seed=$seed 通道 $channel 噪声退化为常量（AD-253 回退）", setOf(1, -1), values)
            }
        }
    }

    @Test
    fun canvasNoiseDiffersBetweenAdjacentPixelsSameSeed() {
        // 「同一 seed 相邻像素噪声不一致」锚点：相邻像素三通道噪声向量
        // 相同的概率仅 1/8——断言聚合差异占比远高于退化形态的 0%。
        val seeds = listOf(0, 1, -1, Int.MIN_VALUE + 5, Int.MAX_VALUE, 0x2F9E1B3C.toInt())
        var differingPairs = 0
        var totalPairs = 0
        for (seed in seeds) {
            for (px in 0 until 4095) {
                totalPairs++
                if (noiseTriple(seed, px) != noiseTriple(seed, px + 1)) differingPairs++
            }
        }
        assertTrue(
            "相邻像素噪声差异占比异常（$differingPairs/$totalPairs）——疑似常量偏移回退",
            differingPairs * 10 > totalPairs * 7,
        )
    }

    // ------------------------------------------------------------- Stage 4

    @Test
    fun stage4LetterboxShieldsScreenAndWindowDynamically() {
        assertTrue("Stage 4 缺少量化函数", script.contains("function roundTo"))
        assertTrue(
            "Stage 4 缺少 screen.* 包装",
            script.contains("Object.getOwnPropertyDescriptor(window.Screen.prototype, 'width')"),
        )
        // AD-259：innerWidth 等改 getter 动态量化（旋转/键盘弹出后读现值）
        assertTrue("Stage 4 缺少窗口维度 getter 包装", script.contains("wrapWindowDimension"))
        assertFalse("窗口维度仍被冻结为取值常量（AD-259 回退）", script.contains("value: roundTo(iw, WS)"))
    }

    // ------------------------------------------------------------- Stage 5

    @Test
    fun stage5QueryStripperWrapsAllExfilChannels() {
        assertTrue("Stage 5 缺少追踪参数表", script.contains("fbclid"))
        assertTrue("Stage 5 缺少 fetch 包装", script.contains("window.fetch = function"))
        assertTrue("Stage 5 缺少 XHR 包装", script.contains("XMLHttpRequest.prototype.open"))
        // AD-285：sendBeacon/WebSocket 同口径 strip
        assertTrue("Stage 5 缺少 sendBeacon 包装（AD-285）", script.contains("navigator.sendBeacon = function"))
        assertTrue("Stage 5 缺少 WebSocket 包装（AD-285）", script.contains("window.WebSocket = function"))
    }

    // ------------------------------------------------------------- Stage 6

    @Test
    fun stage6FontNormalizerKeepsSafeListOnly() {
        assertTrue("Stage 6 缺少 FontFaceSet.check 包装", script.contains("FontFaceSet.prototype.check"))
        assertTrue("Stage 6 缺少安全字体表", script.contains("SAFE_SET"))
    }

    // ------------------------------------------------------------- Stage 7

    @Test
    fun stage7WebglSpoofCoversBothContexts() {
        assertTrue("Stage 7 缺少 WebGL1 伪装", script.contains("WebGLRenderingContext.prototype"))
        assertTrue("Stage 7 缺少 WebGL2 伪装", script.contains("WebGL2RenderingContext.prototype"))
        assertTrue("Stage 7 缺少 MAX_TEXTURE_SIZE 固定", script.contains("0x0D33"))
    }

    // ------------------------------------------------------------- Stage 8

    @Test
    fun stage8TimerPrecisionRoundsNowAndDateNow() {
        assertTrue("Stage 8 缺少 performance.now 包装", script.contains("Object.defineProperty(performance, 'now'"))
        // AD-108：Date.now 只做整数网格取整（无随机分量）——入口必须存在
        assertTrue("Stage 8 缺少 Date.now 整数网格", script.contains("reduceIntegral"))
    }

    // ------------------------------------------------------------- Stage 9

    @Test
    fun stage9ExtProxyInterceptsCwsEndpoints() {
        assertTrue("Stage 9 缺少 CWS 下载拦截", script.contains("""clients2\.google\.com"""))
        assertTrue("Stage 9 缺少拦截告警", script.contains("CWS request intercepted"))
    }

    // ------------------------------------------------------------- 全局

    @Test
    fun protectionVersionFlagIsNonEnumerable() {
        // AD-269：裸赋值（可枚举可删除）→ defineProperty 不可枚举不可配置
        assertTrue(
            "版本标记必须经 defineProperty 注入",
            script.contains("Object.defineProperty(window, '__AEGIS_PROTECTION_VERSION'"),
        )
        assertFalse(
            "版本标记不得再走裸赋值（AD-269 回退）",
            script.contains("window.__AEGIS_PROTECTION_VERSION ="),
        )
    }
}

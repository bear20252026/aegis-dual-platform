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
        assertTrue("Stage 1 缺少 proxyMap 归一查表", script.contains("proxyMap.has(this)"))
    }

    /**
     * AD-297（2026-10-02 审计）：注册键与消费键同源——Stage 1 注册出口与
     * 桥守卫（BRIDGE_GUARD_JS）/Stage 3-9 读取口必须同用
     * Symbol.for('proxy.register.v1')；具名字符串键回退即注册全链空转（键名断言只锁调用形态）。
     */
    @Test
    fun stage1RegisterKeyIsSymbolForSameAsConsumers() {
        assertTrue(
            "Stage 1 注册键必须是 Symbol.for('proxy.register.v1')",
            script.contains("Object.defineProperty(window, Symbol.for('proxy.register.v1'), {"),
        )
        assertFalse("具名注册键调用形态不得残留（AD-297 回退）", script.contains("window, '__AEGIS_REGISTER_PROXY'"))
        assertTrue(
            "桥守卫读取键必须一致（同源契约）",
            WebViewHardening.BRIDGE_GUARD_JS.contains("window[Symbol.for('proxy.register.v1')]"),
        )
        // R8-RS-09（第八轮）：注册资格由闭包窗口标志控制 + 双侧重复登记拒绝 +
        // blob 末尾同步关窗。AD-297 版是裸 set 且 configurable:false ⇒ 零校验且
        // 永不撤销（不可替换就没有关闭通道），比 Rust 侧的 RS-252 更弱。
        // 跨端对账另见 core/rust-policy-core/tests/tostring_window.rs。
        assertTrue("Stage 1 缺闭包内窗口标志", script.contains("var open = true;"))
        assertTrue("注册函数未检查窗口标志", script.contains("if (!open) return;"))
        assertTrue(
            "注册必须拒绝重复的 original 或 proxy",
            script.contains("if (proxyMap.has(original) || proxyMap.has(proxy)) return;"),
        )
        assertTrue("缺 blob 末尾的同步撤销调用", script.contains("if (c) c();"))
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

    /**
     * 审计第六轮（2026-10-03，P1）：站点种子只在闭包内——撤销 window 全局
     * 导出（__AEGIS_SITE_SEED）的回归锚点。种子可被页面按名读取 = 复刻
     * aegisNudge 与三枚 Math.imul 常数即可确定性去噪还原真画布（噪声防护
     * 归零），且具名 __AEGIS_* 全局本身就是防护存在性探针。口径对齐参照
     * 实现 core/rust-policy-core/src/per_site_seed.rs:24-28「站点种子按域
     * 派生后仅存在于闭包内」。
     */
    @Test
    fun stage2SiteSeedIsClosureScopedNeverGlobal() {
        assertTrue("种子必须是闭包局部 const", script.contains("const __AEGIS_SITE_SEED = deriveSeed("))
        assertFalse("种子全局导出不得残留（P1 泄漏回归）", script.contains("window.__AEGIS_SITE_SEED"))
        assertFalse("不得对 window defineProperty 种子", script.contains("defineProperty(window, '__AEGIS_SITE_SEED'"))
        // 两处消费点必须以裸标识符取外层闭包常量（漏一处即该通道失效/回退全局）
        assertTrue("canvas 噪声消费点未取闭包种子", script.contains("parseInt(__AEGIS_SITE_SEED.slice(0, 8), 16)"))
        assertTrue(
            "hardwareConcurrency 消费点未取闭包种子",
            script.contains("parseInt(__AEGIS_SITE_SEED.slice(8, 16), 16)"),
        )
        // 结构不变式：种子声明与最后一个消费点之间 Stage 2 闭包不得提前收口
        // （消费块整体缩进两级内嵌——列 0 的 })(); 只允许出现在消费点之后）
        // 顶层站点框定回归（审计第六轮延续 2026-10-04）：种子必须按**顶层**
        // eTLD+1 派生——按本帧 hostname 派生会让同一第三方跟踪帧在所有站点
        // 产出同一种子（画布哈希=跨站持久标识符，正好废掉本防护）。
        assertTrue(
            "种子派生必须经 aegisTopLevelHostname（ancestorOrigins 通道）",
            script.contains("getETLD1(aegisTopLevelHostname())"),
        )
        assertTrue(
            "祖先链不可用时须保守退回本帧 hostname（不得因取不到顶层而放弃噪声）",
            script.contains("return location.hostname;"),
        )
        assertFalse(
            "不得再按本帧 hostname 直接派生种子（跨站标识符回归）",
            script.contains("getETLD1(location.hostname)"),
        )
        assertTrue(
            "IPv6 字面量 origin 的端口剥离须保留方括号（否则 hostFromOrigin 截半）",
            script.contains("s.charAt(0) === '['"),
        )
        val seedDecl = script.indexOf("const __AEGIS_SITE_SEED =")
        val lastConsumer = script.indexOf("parseInt(__AEGIS_SITE_SEED.slice(8, 16), 16)")
        assertTrue("种子声明必须先于消费点（seedDecl=$seedDecl, consumer=$lastConsumer）", seedDecl in 0 until lastConsumer)
        assertFalse(
            "Stage 2 闭包不得在消费点前提前闭合",
            Regex("(?m)^\\}\\(\\)\\);").containsMatchIn(script.substring(seedDecl, lastConsumer)),
        )
    }

    // ------------------------------------------------------------- Stage 3

    @Test
    fun stage3CanvasNoiseUsesSharedFmixFormula() {
        // R8-RS-01/R8-CS-SEC-04（第八轮）取代 AD-253 口径：三端（Rust shield.rs、
        // Windows FingerprintShield.cs、本端）统一为 murmur3 fmix32 终混 + R/G/B
        // 取 bit0/bit8/bit16。AD-253 那版 `Math.imul(px, 奇数常数) & 1` 的噪声位只由
        // 像素序号奇偶决定（2 个相位）且三通道恒等——扰动宽度不足。
        assertTrue("Stage 3 缺少 fmix32 混合函数", script.contains("function aegisNoiseMix"))
        assertTrue("Stage 3 缺少 fmix32 第一常数", script.contains("Math.imul(m ^ (m >>> 16), 0x85ebca6b)"))
        assertTrue("Stage 3 缺少 fmix32 第二常数", script.contains("Math.imul(m ^ (m >>> 13), 0xc2b2ae35)"))
        assertTrue("Stage 3 缺少 G 通道独立位段", script.contains("((m >>> 8) & 1) !== 0"))
        assertTrue("Stage 3 缺少 B 通道独立位段", script.contains("((m >>> 16) & 1) !== 0"))
        assertFalse("奇数常数 x 像素序号的窄扰动形态仍在", script.contains("Math.imul(px, 0x9E3779B1)"))
        assertFalse("退化常量偏移噪声 (seed + i) 仍在（AD-253 回退）", script.contains("(seed + i)"))
    }

    @Test
    fun stage3CanvasNoiseFormulaReplicaIsNonDegenerate() {
        // 性质断言（与 Rust canvas_noise_formula_is_actually_non_degenerate、
        // C# CanvasNoise_FormulaReplicaIsNonDegenerate 三端同口径）：字符串锚只能
        // 证明「文本长这样」，而第七轮的 RS-249 正是文本看着对、数学上恒退化。
        fun fmix(
            seed: Int,
            px: Int,
        ): Int {
            var m = seed xor px
            m = (m.xor(m ushr 16)).times(0x85ebca6bL.toInt())
            m = (m.xor(m ushr 13)).times(0xc2b2ae35L.toInt())
            return m.xor(m ushr 16)
        }
        val seed = 0x12345678
        // 旧形态：AD-253 乘像素序号（非 4 步进字节偏移）⇒ 噪声位只由奇偶决定，2 个相位
        val phases = (0 until 64).map { (seed xor it.times(0x9E37_79B1L.toInt())) and 1 }.toSet()
        assertEquals("旧公式只有 2 个相位——扰动宽度不足的可复现证明", 2, phases.size)

        val triples =
            (0 until 64).map { px ->
                val m = fmix(seed, px)
                Triple(m and 1, (m ushr 8) and 1, (m ushr 16) and 1)
            }
        assertTrue("噪声位组合过少：${triples.toSet().size}", triples.toSet().size >= 4)
        val identical = triples.count { it.first == it.second && it.second == it.third }
        assertTrue("三通道恒等的像素过多：$identical", identical < 40)
    }

    @Test
    fun stage3ToDataURLHasSizeCap() {
        // AD-270：超尺寸画布直接走原实现（资源放大防护）
        assertTrue("Stage 3 缺少尺寸上限常量", script.contains("MAX_NOISE_PIXELS"))
        assertTrue("Stage 3 缺少超限降级分支", script.contains("origToDataURL.apply(this, arguments)"))
    }

    /**
     * AD-298（2026-10-02 审计）：canvas 读取三通道全覆盖——toDataURL/toBlob/
     * OffscreenCanvas.convertToBlob（漏任一通道 = 噪声绕过；对齐 Rust RS-082）。
     * 三通道共用 applyNoise 单源——噪声形态逐字节同构。
     */
    @Test
    fun stage3CoversAllThreeCanvasReadChannels() {
        assertTrue("toBlob 第二通道必须覆盖", script.contains("HTMLCanvasElement.prototype.toBlob"))
        assertTrue("convertToBlob 第三通道必须覆盖", script.contains("OffscreenCanvas.prototype.convertToBlob"))
        assertTrue("OffscreenCanvas 缺失环境须空转守卫", script.contains("typeof OffscreenCanvas !== 'undefined'"))
        // 三通道共用同一噪声实现（形态一致——不出现第二份噪声循环）
        assertEquals("噪声循环必须单源共享（三通道同构）", 1, Regex("for \\(let px = 0, i = 0").findAll(script).count())
    }

    /** AD-311（2026-10-02 审计）：aegisNudge 的 Kotlin 镜像（0/255 边界离岸）。 */
    private fun aegisNudge(
        current: Int,
        noiseBit: Boolean,
    ): Int =
        when (current) {
            0 -> 1
            255 -> 254
            else -> if (noiseBit) current + 1 else current - 1
        }

    @Test
    fun stage3BoundaryNoiseTakesOffshoreDirection() {
        // 0/255 边界：Uint8ClampedArray 的 clamp 会吸收向岸噪声（0-1→0、
        // 255+1→255）——边界像素噪声必须取离岸方向（0→+1、255→-1）。
        assertTrue("Stage 3 缺少边界离岸函数", script.contains("function aegisNudge"))
        assertTrue("0 边界离岸缺失", script.contains("if (current === 0) return 1;"))
        assertTrue("255 边界离岸缺失", script.contains("if (current === 255) return 254;"))
        // Kotlin 镜像同口径：边界恒离岸；中间值随噪声位 ±1
        assertEquals(1, aegisNudge(0, noiseBit = false))
        assertEquals(1, aegisNudge(0, noiseBit = true))
        assertEquals(254, aegisNudge(255, noiseBit = false))
        assertEquals(254, aegisNudge(255, noiseBit = true))
        assertEquals(99, aegisNudge(100, noiseBit = false))
        assertEquals(101, aegisNudge(100, noiseBit = true))
    }

    /**
     * AD-314（2026-10-02 审计）：Stage 3-9 每个包装点必须存在 __aegisReg
     * 注册行——漏注册即该包装 toString() 暴露源码（品牌特征一行可探）。
     */
    @Test
    fun stage3To9EveryWrapperRegistersToStringGuard() {
        val expectedRegistrations =
            listOf(
                "if (__aegisReg) __aegisReg(HTMLCanvasElement.prototype.toDataURL, origToDataURL);",
                "if (__aegisReg) __aegisReg(HTMLCanvasElement.prototype.toBlob, origToBlob);",
                "if (__aegisReg) __aegisReg(OffscreenCanvas.prototype.convertToBlob, origConvert);",
                "if (__aegisReg) __aegisReg(window.fetch, origFetch);", // Stage 5 + Stage 9 各一次
                "if (__aegisReg) __aegisReg(XMLHttpRequest.prototype.open, origOpen);",
                "if (__aegisReg) __aegisReg(navigator.sendBeacon, origBeacon);",
                "if (__aegisReg) __aegisReg(window.WebSocket, OrigWS);",
                "if (__aegisReg) __aegisReg(FontFaceSet.prototype.check, origCheck);",
                "if (__aegisReg) __aegisReg(proto.getParameter, orig);",
                "if (__aegisReg) __aegisReg(nowWrapper, o);",
                "if (__aegisReg) __aegisReg(dateWrapper, d);",
            )
        expectedRegistrations.forEach { line ->
            assertTrue("缺少包装注册行：$line", script.contains(line))
        }
        // fetch 被 Stage 5 与 Stage 9 各包装一次——两处都要注册
        assertEquals(
            "Stage 5/Stage 9 的 fetch 包装都必须注册",
            2,
            Regex(Regex.escape("if (__aegisReg) __aegisReg(window.fetch, origFetch);")).findAll(script).count(),
        )
    }

    /** AD-310（2026-10-02 审计）：MAX_VIEWPORT_DIMS 伪装类型对齐真机 Int32Array。 */
    @Test
    fun stage7MaxViewportDimsSpoofsInt32Array() {
        assertTrue("0x0D3A 必须返回 Int32Array", script.contains("new Int32Array([16384, 16384])"))
        assertFalse("Float32Array 伪装不得残留（AD-310 回退）", script.contains("new Float32Array([16384, 16384])"))
    }

    /**
     * AD-329（2026-10-02 审计）：高频两段公共后缀表补齐——表内条目命中才
     * 折叠为公共后缀；本表即「同后缀两站种子不同」回归断言的例外清单。
     */
    @Test
    fun stage2PublicSuffixTableCoversHighFrequencyTwoLabelSuffixes() {
        val suffixes =
            listOf(
                "co.il",
                "org.il",
                "com.ua",
                "com.pl",
                "com.gr",
                "com.pt",
                "com.ro",
                "com.sa",
                "com.pk",
            )
        suffixes.forEach { suffix ->
            assertTrue("迷你 PSL 缺少高频两段后缀 $suffix（AD-329）", script.contains("'$suffix'"))
        }
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
        // R8-RS-04：单调高水位三件套齐在；断**次数**而非「标识符在场」——
        // 只声明却不在读回路径上比较/回填，等于没有钳位（恒绿的另一种形态）。
        assertTrue("Stage 8 缺单调高水位声明", script.contains("var lastPerf = -Infinity;"))
        assertEquals("Stage 8 钳位形态不完整", 4, "lastPerf".toRegex().findAll(script).count())
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

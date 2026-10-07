package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * BUG-001 / BUG-006 回归锁的正身（R8-SH-15，第八轮审计 2026-10-05）。
 *
 * 这两条回归锁原本写在 `tests/ui-regression/start_page.test.mjs` 里，判的是
 * **首页 shell 脚本**（`shared/shell/` 下四个 JS 文件）：
 * - BUG-001：正则判 shell JS 里不出现 Android 的 `setTag` 调用——JS 里永远不会
 *   出现这个 API 名 ⇒ 断言恒真；
 * - BUG-006：正则判 shell JS 里不出现 Kotlin 的 `setOf` 通配写法——同理恒真。
 * 于是这两个「回归锁」对 BUG-001/BUG-006 零保护，而台账一直记着它们绿。
 *
 * 本文件把锁搬到真正的语料上：被保护的代码在 `android/app`，判据也必须读那里。
 * 两条防自己失效的锚：
 * 1. [corpusContainsTheConstructsTheLocksClaimToWatch]——正面控制。语料里没有
 *    被观察的结构时，「不含禁止形态」这类断言会永远为真，所以先断它「在」；
 * 2. 禁止形态只在**剔除注释后的代码行**上判——SecureWebViewFactory 第 26 行与
 *    WebViewHardening 第 39 行的历史教训注释里就写着 framework 生成的 view id
 *    与 https 全域通配原文，不剔注释会被自己的注释打红（第八轮 #97 同款事故）。
 *
 * （KDoc 正文里刻意不复现那两条 JS 正则原文：里面的转义星号加斜杠会提前闭合
 * 块注释——本文件第一版就是被 KtLint「failed to parse」当场拒绝的。）
 */
class DocumentStartInjectionRegressionTest {
    private fun repoRoot(): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val candidate = File(dir, HARDENING_PATH)
            if (candidate.isFile) {
                return dir!!
            }
            dir = dir?.parentFile
        }
        error("未找到 $HARDENING_PATH（请在仓库内运行测试）")
    }

    private fun read(relative: String): String {
        val file = File(repoRoot(), relative)
        assertTrue("回归锁语料缺失：$relative", file.isFile)
        return file.readText()
    }

    /** 剔除注释行后的代码文本——禁止形态只可能在代码里成立。 */
    private fun codeOnly(relative: String): String {
        val raw = read(relative).replace("\r\n", "\n")
        val out = mutableListOf<String>()
        for (line in raw.split("\n")) {
            val trimmed = line.trim()
            val isComment = trimmed.startsWith("//") || trimmed.startsWith("/*") || trimmed.startsWith("*")
            if (!isComment) {
                out += trimmed
            }
        }
        return out.joinToString("\n")
    }

    /** R8-CS-SEC-14：注入文本按 Stage 边界拆到三个文件——锚必须读三段之和，
     *  否则「wildcard 随脚本搬进子文件」这类回归正好落在盲区里。 */
    private fun hardeningCode(): String =
        codeOnly(HARDENING_PATH) +
            codeOnly(HARDENING_SEED_PATH) +
            codeOnly(HARDENING_CANVAS_PATH) +
            codeOnly(HARDENING_TAIL_PATH)

    @Test
    fun corpusContainsTheConstructsTheLocksClaimToWatch() {
        // 正面控制：先证明「被观察的东西确实在语料里」，否则下面的恒真断言毫无意义
        val hardening = hardeningCode()
        assertTrue(hardening.contains("val allowedOrigins = setOf("))
        assertTrue(hardening.contains("WebViewFeature.DOCUMENT_START_SCRIPT"))
        val factory = codeOnly(FACTORY_PATH)
        assertTrue(factory.contains("ConcurrentHashMap<WebView, SecureNavigator>"))
        val proguard = read(PROGUARD_PATH)
        assertTrue(proguard.contains("-keep class androidx.webkit.R\$id { *; }"))
    }

    @Test
    fun bug001TagKeyDoesNotUseFrameworkGeneratedId() {
        // 历史教训一：View.setTag(generateViewId(), ...) ——generateViewId() 的
        // package id 落在 0x01（framework 区段），而 setTag(int, ...) 要求
        // ≥0x02 的应用资源 id，真机启动必崩。
        assertFalse(codeOnly(FACTORY_PATH).contains("generateViewId"))
        assertFalse(hardeningCode().contains("generateViewId"))
        assertFalse(codeOnly(FACTORY_PATH).contains("View.generateViewId"))
        // 历史教训二（H-4）：WeakHashMap 存导航器——值强引用键（WebView），
        // 键永不可达、条目永不回收，每开一个标签泄漏一个 WebView。
        assertFalse(codeOnly(FACTORY_PATH).contains("WeakHashMap<WebView"))
    }

    @Test
    fun bug006AllowedOriginRulesDoesNotUseSchemeWildcard() {
        // 历史教训：AndroidX 对 "https://*" 形态直接 IllegalArgumentException，
        // document-start 注入整条链失效。合法的全源写法只有单星号 "*"。
        val hardening = hardeningCode()
        val schemeWildcard = "\"https://*\""
        assertFalse(hardening.contains(schemeWildcard))
        assertFalse(hardening.contains("\"http://*\""))
    }

    companion object {
        // R8-CS-SEC-14：注入文本拆到三个文件（主文件 + Stage 1-3 + Stage 4-9）。
        private const val HARDENING_PATH =
            "android/app/src/main/java/com/aegis/browser/WebViewHardening.kt"
        private const val HARDENING_SEED_PATH =
            "android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesSeed.kt"
        private const val HARDENING_TAIL_PATH =
            "android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt"

        // ⑦（第八轮）：Stage 3 的 canvas 文本再外迁一份，语料面必须跟着长
        private const val HARDENING_CANVAS_PATH =
            "android/app/src/main/java/com/aegis/browser/WebViewHardeningCanvas.kt"
        private const val FACTORY_PATH =
            "android/app/src/main/java/com/aegis/browser/SecureWebViewFactory.kt"
        private const val PROGUARD_PATH = "android/app/proguard-rules.pro"
    }
}

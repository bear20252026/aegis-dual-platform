package com.aegis.browser

import android.webkit.WebView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.aegis.broker.AndroidBroker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * AD-067（2026-09-24 审计）：instrumented 冒烟集——真机/模拟器最小走查，
 * 覆盖「进程包名正确 + Broker 会话生命周期 + 关键纯逻辑在真 ART 上语义一致」。
 * CI 无模拟器不执行（assembleDebugAndroidTest 编译验证即可），真机批次运行。
 */
@RunWith(AndroidJUnit4::class)
class SmokeInstrumentedTest {
    @Test
    fun targetPackageIsAegis() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        // AD-288（2026-10-01 审计）：debug 构建带 .debug 后缀（applicationIdSuffix）
        // ——instrumented 面锁 debug 包名；release/distribution 保持
        // com.aegis.browser（e2e 脚本与发布链契约）。
        assertEquals("com.aegis.browser.debug", context.packageName)
    }

    /**
     * AD-276（2026-10-01 审计）：safeBrowsingEnabled=true 此前零自动化断言
     * （注释称真机覆盖，实际不存在）。getSafeBrowsingEnabled 是 API 26+
     * getter——JVM/Robolectric 侧无实现（恒 false），在真机/模拟器断言。
     */
    @Test
    fun safeBrowsingIsEnabledAfterEngineConfigure() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        var assertionError: AssertionError? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            try {
                val wv = WebView(context)
                try {
                    BrowserEngine(wv).configure()
                    assertTrue("safeBrowsingEnabled 必须为 true（AD-276）", wv.settings.safeBrowsingEnabled)
                } finally {
                    wv.destroy()
                }
            } catch (e: AssertionError) {
                assertionError = e
            }
        }
        assertionError?.let { throw it }
    }

    @Test
    fun brokerSessionLifecycleWorksOnDevice() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-smoke", "tab-smoke"))
        val decision =
            broker.evaluateNavigation("session-smoke", "tab-smoke", 0, "https://example.com/", "navigation")
        assertTrue(decision is com.aegis.broker.Decision.Allow)
        val action = (decision as com.aegis.broker.Decision.Allow).action
        assertTrue(broker.isValid(action, 0))
        broker.destroySession("session-smoke")
        assertFalse(broker.isValid(action, 0))
    }

    @Test
    fun searchEnginesNormalizeMatchesJvmSemanticsOnDevice() {
        // AD-057 uriEncode 纯字符串化——真 ART 与 JVM 语义一致（防平台差异回归）
        assertEquals(
            "https://www.baidu.com/s?wd=rust%20uniffi",
            SearchEngines.normalizeInput("rust uniffi", "baidu"),
        )
        assertEquals("a/b", SearchEngines.uriEncode("a/b"))
    }

    @Test
    fun downloadHandlerNameResolutionMatchesJvmSemanticsOnDevice() {
        // AD-032/AD-027 链路在真 ART 上语义一致
        assertEquals(
            "report.pdf",
            WebViewDownloadHandler.resolveDownloadFileName(
                "https://c.d/redirect",
                "",
                "attachment; filename=\"report.pdf\"",
            ),
        )
    }

    @Test
    fun perSiteSeedSha256KnownAnswerOnDevice() {
        // AD-005（审计 2026-09-23 清单·真机批次）：per-site 种子派生迁移为
        // JS 内嵌同步 SHA-256（构造对齐 Rust per_site_seed：hexDecode(sessionSeed)
        // || 'aegis:per-site-seed:v2:' || domain，取前 16 字节）。JVM 无法执行
        // WebView JS——在模拟器真 Chromium 上对 Kotlin MessageDigest 已知答案。
        //
        // 审计第六轮（2026-10-03）：探针改黑箱——站点种子不再导出为
        // window.__AEGIS_SITE_SEED 全局（页面可读 = 噪声可确定性去除 + 跨站
        // 标识符），本用例此前正是靠那个全局读种子。现改经「闭包内消费者」
        // 反证派生正确：hardwareConcurrency = 2 + (种子[8,16) mod 7)，并由
        // 已知答案直接核算；同时断言全局确实已消失（泄漏回归即红）。
        val sessionSeed = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
        val domain = "example.com"
        val md = java.security.MessageDigest.getInstance("SHA-256")
        md.update(sessionSeed.chunked(2).map { it.toInt(16).toByte() }.toByteArray())
        md.update("aegis:per-site-seed:v2:".toByteArray(Charsets.US_ASCII))
        md.update(domain.toByteArray(Charsets.UTF_8))
        val expected = md.digest().take(16).joinToString("") { "%02x".format(it) }
        val expectedHardwareConcurrency = 2 + (expected.substring(8, 16).toLong(16) % 7)

        // 测试锚点替换：脚本派生入参从 location.hostname 固定为已知域名
        // （仅测试副本做字符串手术，生产脚本不含该替换）
        val script =
            WebViewHardening
                .fingerprintShieldScript(sessionSeed)
                .replace("getETLD1(location.hostname)", "'example.com'")

        val latch = CountDownLatch(1)
        var probe: String? = null
        var webView: WebView? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            webView = WebView(InstrumentationRegistry.getInstrumentation().targetContext)
            webView!!.settings.javaScriptEnabled = true
            webView!!.evaluateJavascript(script) {
                // 单表达式取两观测：typeof 种子全局 | hardwareConcurrency 实测
                webView!!.evaluateJavascript(
                    "(function(){return typeof window.__AEGIS_SITE_SEED + '|' + navigator.hardwareConcurrency;})()",
                ) { result ->
                    probe = result.trim().removeSurrounding("\"")
                    latch.countDown()
                }
            }
        }
        assertTrue("evaluateJavascript 未在 30s 内回传", latch.await(30, TimeUnit.SECONDS))
        InstrumentationRegistry.getInstrumentation().runOnMainSync { webView?.destroy() }
        assertEquals("站点种子全局不得存在（审计第六轮：闭包封装泄漏回归）", "undefined", probe?.substringBefore('|'))
        assertEquals(
            "JS 闭包内 SHA-256 派生与 JVM MessageDigest 已知答案不一致（经消费者侧反证）",
            expectedHardwareConcurrency.toString(),
            probe?.substringAfter('|'),
        )
    }
}

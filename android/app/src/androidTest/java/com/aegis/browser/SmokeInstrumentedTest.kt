package com.aegis.browser

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.aegis.broker.AndroidBroker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

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
        assertEquals("com.aegis.browser", context.packageName)
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
}

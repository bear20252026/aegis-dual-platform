package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * WebViewVersionCheck.isOutdated 阈值边界 JVM 单测（2026-09-24 审计——AD-030）。
 * 阈值 = 132_000_000（CVE-2026-12438/11295 防御线——随安全公告维护）。
 */
class WebViewVersionCheckTest {
    private val threshold = 132_000_000

    @Test
    fun belowThresholdIsOutdated() {
        assertTrue(WebViewVersionCheck.isOutdated(threshold - 1))
        assertTrue(WebViewVersionCheck.isOutdated(0))
        assertTrue(WebViewVersionCheck.isOutdated(-1))
    }

    @Test
    fun atOrAboveThresholdIsNotOutdated() {
        // 恰好等于阈值不告警（>= 安全版本即放行——boundary 断言防 off-by-one）
        assertFalse(WebViewVersionCheck.isOutdated(threshold))
        assertFalse(WebViewVersionCheck.isOutdated(threshold + 1))
        assertFalse(WebViewVersionCheck.isOutdated(Int.MAX_VALUE))
    }
}

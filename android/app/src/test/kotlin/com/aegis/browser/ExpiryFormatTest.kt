package com.aegis.browser

import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId

/**
 * AD-110（审计 2026-09-23 清单·A6 批）：审批对话框过期时刻格式化单测——
 * Instant.toString()（ISO-8601）换用户可读 `yyyy-MM-dd HH:mm`（注入时区）。
 */
class ExpiryFormatTest {
    @Test
    fun formatsEpochInstantInFixedZone() {
        // 2023-11-14T22:13:20Z（审批向量中的 expires_at 时刻）
        val instant = Instant.fromEpochSeconds(1_700_000_000)
        assertEquals("2023-11-14 22:13", ExpiryFormat.format(instant, ZoneId.of("UTC")))
    }

    @Test
    fun shanghaiOffsetShiftsWallClock() {
        val instant = Instant.fromEpochSeconds(1_700_000_000)
        assertEquals("2023-11-15 06:13", ExpiryFormat.format(instant, ZoneId.of("Asia/Shanghai")))
    }

    @Test
    fun defaultZoneRenderableAsUserFacingPattern() {
        val rendered = ExpiryFormat.format(Instant.fromEpochSeconds(1_700_000_000))
        assertTrue(
            "默认时区输出仍须为 yyyy-MM-dd HH:mm 形态: $rendered",
            Regex("^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$").matches(rendered),
        )
    }
}

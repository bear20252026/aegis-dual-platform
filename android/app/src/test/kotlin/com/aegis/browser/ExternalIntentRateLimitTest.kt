package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * AD-302（2026-10-02 审计）：外链 VIEW intent 频控状态机 JVM 单测——
 * data=null / action≠VIEW 的 intent 不烧频控窗口（原实现判 intent.data 前
 * 推进时间戳，空 intent 也把后续真实外链挡在窗口外——打断面）。
 */
class ExternalIntentRateLimitTest {
    @Test
    fun nonConsumableIntentsDoNotBurnWindow() {
        val limit = ExternalIntentRateLimit(minIntervalMs = 1_000L)
        // 连续空 intent（data=null / action≠VIEW）：不消费也不烧窗口
        assertFalse(limit.tryAcquire(now = 100L, hasConsumableIntent = false))
        assertFalse(limit.tryAcquire(now = 105L, hasConsumableIntent = false))
        // 紧随其后的真实外链立即可消费（窗口未被空 intent 烧掉）
        assertTrue(limit.tryAcquire(now = 110L, hasConsumableIntent = true))
    }

    @Test
    fun repeatedConsumptionInsideWindowIsDropped() {
        val limit = ExternalIntentRateLimit(minIntervalMs = 1_000L)
        assertTrue(limit.tryAcquire(now = 100L, hasConsumableIntent = true))
        // 窗口期内的重复 intent 静默丢弃（AD-283 语义保持）
        assertFalse(limit.tryAcquire(now = 500L, hasConsumableIntent = true))
        assertFalse(limit.tryAcquire(now = 1_099L, hasConsumableIntent = true))
        // 窗口过后恢复
        assertTrue(limit.tryAcquire(now = 1_100L, hasConsumableIntent = true))
    }

    @Test
    fun firstConsumptionAlwaysPassesFromColdStart() {
        // 冷启动（lastConsumedAt=0）：首个真实外链不受窗口约束
        val limit = ExternalIntentRateLimit(minIntervalMs = 1_500L)
        assertTrue(limit.tryAcquire(now = 1L, hasConsumableIntent = true))
    }
}

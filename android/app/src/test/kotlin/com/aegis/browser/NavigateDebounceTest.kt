package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * AD-157（审计 2026-09-23 清单·A7 批）：防抖窗口行为 JVM 单测——时钟经
 * 构造注入（假时钟逐毫秒驱动），锁定四条窗口语义：
 * ①窗口外首次尝试放行并推进锚点；②窗口内重复尝试拒绝；
 * ③窗口边界（elapsed == intervalMs）放行；④待审批挂起一律拒绝且不推进
 * 锚点（挂起不消耗防抖窗口——恢复后首个尝试按窗口语义重新裁决）。
 */
class NavigateDebounceTest {
    /** 可编程假时钟（单调语义由测试自己保证——只前进不回拨）。 */
    private class FakeClock {
        var current: Long = 0

        fun now(): Long = current
    }

    @Test
    fun firstAttemptOutsideWindowIsAllowedAndAdvancesAnchor() {
        val clock = FakeClock()
        val debounce = NavigateDebounce(intervalMs = 500L, now = clock::now)
        clock.current = 1_000L
        assertTrue(debounce.ok(pendingConfirmationActive = false))
        // 窗口内（锚点 + 1ms）重复尝试被拒
        clock.current = 1_001L
        assertFalse(debounce.ok(pendingConfirmationActive = false))
    }

    @Test
    fun attemptInsideWindowIsRejected() {
        val clock = FakeClock()
        val debounce = NavigateDebounce(intervalMs = 500L, now = clock::now)
        clock.current = 1_000L
        assertTrue(debounce.ok(pendingConfirmationActive = false))
        clock.current = 1_499L
        assertFalse("窗口内（499ms < 500ms）必须拒绝", debounce.ok(pendingConfirmationActive = false))
    }

    @Test
    fun attemptAtWindowBoundaryIsAllowed() {
        val clock = FakeClock()
        val debounce = NavigateDebounce(intervalMs = 500L, now = clock::now)
        clock.current = 1_000L
        assertTrue(debounce.ok(pendingConfirmationActive = false))
        clock.current = 1_500L
        assertTrue("elapsed == intervalMs 属窗口外（>= 语义）", debounce.ok(pendingConfirmationActive = false))
    }

    @Test
    fun pendingConfirmationSuppressesAttemptWithoutAdvancingAnchor() {
        val clock = FakeClock()
        val debounce = NavigateDebounce(intervalMs = 500L, now = clock::now)
        clock.current = 1_000L
        assertTrue(debounce.ok(pendingConfirmationActive = false))
        // 挂起期间（无论过了多久）一律拒绝
        clock.current = 9_999L
        assertFalse("待审批挂起中不得放行", debounce.ok(pendingConfirmationActive = true))
        // 挂起拒绝不推进锚点：解除挂起后按「距原锚点」裁决（此时早已出窗）
        clock.current = 10_000L
        assertTrue(debounce.ok(pendingConfirmationActive = false))
    }
}

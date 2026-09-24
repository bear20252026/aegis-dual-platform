package com.aegis.broker

import kotlinx.datetime.Instant
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * AndroidBroker P1 测试缺口补齐（2026-09-24 审计批次 A2——AD-016..020）。
 *
 * - AD-016：registerSession 四类非法输入拒绝
 * - AD-017：已消费 nonce FIFO 有界性（逐出最旧——有界内存）
 * - AD-018：consumeNavigation 参数不匹配拒绝（origin/scope/tab/参数矩阵）
 * - AD-019：policyVersion 不匹配拒绝（isValid/consumeNavigation 双门）
 * - AD-020：SESSION_TTL 过期边界（时钟注入后可测——滑动过期防退化）
 */
class AndroidBrokerPolicyTtlTest {
    // ---------------------------------------------------------------- AD-016
    @Test
    fun registerSessionRejectsFourClassesOfInvalidInput() {
        val broker = AndroidBroker()
        // ① sessionId 空白
        assertFalse(broker.registerSession("", "tab-1"))
        assertFalse(broker.registerSession("   ", "tab-1"))
        // ② tabId 空白
        assertFalse(broker.registerSession("session-1", ""))
        assertFalse(broker.registerSession("session-1", "   "))
        // ③ generation 负数
        assertFalse(broker.registerSession("session-1", "tab-1", generation = -1))
        // ④ 重复 sessionId（二次注册必须失败——防会话覆盖）
        assertTrue(broker.registerSession("session-dup", "tab-1"))
        assertFalse(broker.registerSession("session-dup", "tab-other"))
    }

    // ---------------------------------------------------------------- AD-017
    @Test
    fun consumedNoncesAreBoundedWithFifoEviction() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))

        val firstAction = issueAllowedAction(broker, 0)
        consume(broker, firstAction, 0)

        // 耗尽上限（MAX_CONSUMED_NONCES）：first 之外再消费 MAX 条
        val middleActions =
            (1..AndroidBroker.MAX_CONSUMED_NONCES).map { i -> issueAllowedAction(broker, i.toLong()) }
        middleActions.forEachIndexed { i, action -> consume(broker, action, i.toLong() + 1) }

        // 有界性实证一：最新 nonce 仍在册——重放被拒
        val latestAction = middleActions.last()
        assertFalse(
            "最新 nonce 不得被逐出重放",
            broker.consumeNavigation(
                latestAction,
                "session-1",
                "tab-1",
                latestAction.documentGeneration,
                urlForIndex(AndroidBroker.MAX_CONSUMED_NONCES.toLong()),
                "navigation",
            ),
        )
        // 有界性实证二：最旧 nonce 已被 FIFO 逐出——对应授权在 TTL 内可再消费
        // （文档化权衡：逐出 nonce 的授权对象 SESSION_TTL_SECONDS 内即过期——
        // 重放窗口远小于逐出周期，见 MAX_CONSUMED_NONCES 注释）
        assertTrue(
            "最旧 nonce 应已被 FIFO 逐出（可再次消费）",
            broker.consumeNavigation(
                firstAction,
                "session-1",
                "tab-1",
                firstAction.documentGeneration,
                urlForIndex(0),
                "navigation",
            ),
        )
    }

    private fun issueAllowedAction(
        broker: AndroidBroker,
        index: Long,
    ): AuthorizedAction {
        val decision =
            broker.evaluateNavigation(
                sessionId = "session-1",
                tabId = "tab-1",
                generation = 0,
                rawUrl = urlForIndex(index),
                scope = "navigation",
            )
        assertTrue(decision is Decision.Allow)
        return (decision as Decision.Allow).action
    }

    private fun consume(
        broker: AndroidBroker,
        action: AuthorizedAction,
        index: Long,
    ): Boolean =
        broker.consumeNavigation(
            action,
            "session-1",
            "tab-1",
            action.documentGeneration,
            urlForIndex(index),
            "navigation",
        )

    private fun urlForIndex(index: Long): String = "https://example.com/p$index"

    // ---------------------------------------------------------------- AD-018
    @Test
    fun consumeNavigationRejectsParameterMismatches() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))
        val decision =
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com/a?b=1",
                "navigation",
            )
        assertTrue(decision is Decision.Allow)
        val action = (decision as Decision.Allow).action

        fun consumeWith(
            rawUrl: String = "https://example.com/a?b=1",
            scope: String = "navigation",
            tabId: String = "tab-1",
        ): Boolean = broker.consumeNavigation(action, "session-1", tabId, 0, rawUrl, scope)

        // ① origin 不匹配（不同 host）
        assertFalse(consumeWith(rawUrl = "https://evil.example/a?b=1"))
        // ② canonicalParameters 不匹配（不同 path / query）
        assertFalse(consumeWith(rawUrl = "https://example.com/other?b=1"))
        assertFalse(consumeWith(rawUrl = "https://example.com/a?b=2"))
        // ③ scope 不匹配
        assertFalse(consumeWith(scope = "download"))
        // ④ tabId 不匹配
        assertFalse(consumeWith(tabId = "tab-2"))
        // ⑤ 全部匹配恰好一次成功（矩阵对照）
        assertTrue(consumeWith())
        // ⑥ 成功后 nonce 一次性——同参重放拒绝
        assertFalse(consumeWith())
    }

    // ---------------------------------------------------------------- AD-019
    @Test
    fun policyVersionMismatchIsRejected() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))
        val decision =
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            )
        assertTrue(decision is Decision.Allow)
        val action = (decision as Decision.Allow).action

        // 策略版本被篡改的授权——isValid/consumeNavigation 双门拒绝
        val forged = action.copy(policyVersion = "9.9")
        assertFalse(broker.isValid(forged, 0))
        assertFalse(
            broker.consumeNavigation(forged, "session-1", "tab-1", 0, "https://example.com", "navigation"),
        )

        // 对照：policyVersion 一致才有效（nonce 未消费前）
        assertTrue(broker.isValid(action, 0))
    }

    // ---------------------------------------------------------------- AD-020
    @Test
    fun sessionTtlExpiryIsTestableWithInjectedClock() {
        val t0 = Instant.parse("2026-09-24T00:00:00Z")
        val clock = FakeClock(t0)
        val broker = AndroidBroker(clock = clock)
        assertTrue(broker.registerSession("session-1", "tab-1"))
        val decision =
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            )
        assertTrue(decision is Decision.Allow)
        val action = (decision as Decision.Allow).action

        // TTL = SESSION_TTL_SECONDS：签发时有效
        assertTrue(broker.isValid(action, 0))
        // +119s：仍在 TTL 内
        clock.instant = t0.plus(kotlin.time.Duration.parse("119s"))
        assertTrue(broker.isValid(action, 0))
        // +120s：恰好到界——expiresAt > now 不成立（fail-closed）
        clock.instant = t0.plus(kotlin.time.Duration.parse("${AndroidBroker.SESSION_TTL_SECONDS}s"))
        assertFalse(broker.isValid(action, 0))
        // 过期授权不可消费
        assertFalse(
            broker.consumeNavigation(action, "session-1", "tab-1", 0, "https://example.com", "navigation"),
        )
    }

    /** 可注入时钟（AD-020）——固定 instant 手动推进。 */
    private class FakeClock(
        var instant: Instant,
    ) : kotlinx.datetime.Clock {
        override fun now(): Instant = instant
    }
}

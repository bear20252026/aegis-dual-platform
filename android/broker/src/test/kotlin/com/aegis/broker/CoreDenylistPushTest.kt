package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 分批协议的常跑用例（R9-B95）——**没有 .so 也能全跑**，这是 R8-CI-18 那一课的直接结果：
 * 真 JNI 路径的用例在 PR 门禁里集体早退，等于没有覆盖。
 *
 * 每张假核心都记录「收到哪些 (批大小, 档位)」，因为本批要防的正是**顺序/档位**出错：
 * 暂存会话没开就追加、提交前就以为生效、旧核心上假装拿到原子性，都是
 * 「名单看起来在，实际拦不住」的形态。
 */
class CoreDenylistPushTest {
    private class FakeCore(
        private val acks: List<CoreDenylistPush.Ack>,
        private val failAt: Int? = null,
    ) {
        val received = mutableListOf<Pair<Int, Int>>()

        fun send(
            batch: List<String>,
            mode: Int,
        ): CoreDenylistPush.Ack {
            val index = received.size
            received += batch.size to mode
            if (failAt == index) {
                return REFUSED
            }
            return acks[index]
        }
    }

    @Test
    fun emptySnapshotIsOneReplaceAndReportsPublishedZero() {
        val core = FakeCore(listOf(newCore(0)))
        val result = CoreDenylistPush.drive(listOf(emptyList()), 0, core::send)
        assertEquals(listOf(0 to CoreDenylistPush.MODE_REPLACE), core.received)
        assertEquals(CoreDenylistOutcome.Published, result.outcome)
        assertEquals(0, result.accepted)
    }

    @Test
    fun singleBatchUsesAtomicReplaceWithoutOpeningASession() {
        val core = FakeCore(listOf(newCore(1)))
        val result = CoreDenylistPush.drive(listOf(listOf("a.example")), 1, core::send)
        assertEquals(listOf(1 to CoreDenylistPush.MODE_REPLACE), core.received)
        assertEquals(CoreDenylistOutcome.Published, result.outcome)
        assertEquals("single_batch", result.detail)
    }

    @Test
    fun multiBatchOnNewCoreGoesBeginAppendAppendCommit() {
        val core =
            FakeCore(
                listOf(newCore(1), newCore(1), newCore(1), newCore(0, staged = true)),
            )
        val batches = listOf(listOf("a.example"), listOf("b.example"), listOf("c.example"))
        val result = CoreDenylistPush.drive(batches, 3, core::send)
        assertEquals(
            listOf(
                1 to CoreDenylistPush.MODE_BEGIN,
                1 to CoreDenylistPush.MODE_APPEND,
                1 to CoreDenylistPush.MODE_APPEND,
                0 to CoreDenylistPush.MODE_COMMIT,
            ),
            core.received,
        )
        assertEquals(CoreDenylistOutcome.Published, result.outcome)
        assertEquals(3, result.accepted)
        assertEquals("staged_commit", result.detail)
    }

    @Test
    fun appendFailureAbortsAndNeverCommits() {
        val core = FakeCore(listOf(newCore(1), newCore(1)), failAt = 2)
        val batches = listOf(listOf("a.example"), listOf("b.example"), listOf("c.example"))
        val result = CoreDenylistPush.drive(batches, 3, core::send)
        assertEquals(CoreDenylistOutcome.NotPublished, result.outcome)
        assertTrue(result.detail.contains("denylist_staged_push_aborted@2"))
        // 措辞必须是「未提交 + 核心仍服务上一份完整快照」——"保留前缀"那种半截话掩盖了原子性
        assertTrue(result.detail.contains("未提交"))
        assertTrue(result.detail.contains("上一份完整黑名单快照"))
        assertTrue("中止后不得再发提交批", core.received.none { it.second == CoreDenylistPush.MODE_COMMIT })
    }

    @Test
    fun commitRefusedIsReportedAsNotPublished() {
        val refusedByCore = CoreDenylistPush.Ack(true, 0, 0, true, true, false, "commit refused")
        val core = FakeCore(listOf(newCore(1), newCore(1), refusedByCore))
        val result = CoreDenylistPush.drive(listOf(listOf("a.example"), listOf("b.example")), 2, core::send)
        assertEquals(CoreDenylistOutcome.NotPublished, result.outcome)
        assertEquals("denylist_commit_refused", result.detail)
        assertTrue(core.received.last() == 0 to CoreDenylistPush.MODE_COMMIT)
    }

    @Test
    fun legacyCoreWithoutModeEchoFallsBackToBeginThenAppend() {
        val legacyAcks = List(3) { legacyCore(accepted = 1, clearEcho = true) }
        val core = FakeCore(legacyAcks)
        val batches = listOf(listOf("a.example"), listOf("b.example"), listOf("c.example"))
        val result = CoreDenylistPush.drive(batches, 3, core::send)
        assertEquals(
            listOf(
                1 to CoreDenylistPush.MODE_BEGIN,
                1 to CoreDenylistPush.MODE_APPEND,
                1 to CoreDenylistPush.MODE_APPEND,
            ),
            core.received,
        )
        assertTrue("旧核心路径不得发提交", core.received.none { it.second == CoreDenylistPush.MODE_COMMIT })
        assertEquals(CoreDenylistOutcome.Published, result.outcome)
        assertEquals("legacy_replace_then_append", result.detail)
    }

    @Test
    fun legacyCoreWithoutClearEchoStopsAndNamesTheResidualPrefix() {
        // 首批不回显 clear = 2 参旧核心：它忽略档位实参并按整批替换行事 ⇒
        // 继续推完只会让名单变成「最后一批」。必须中止，并把保留的前缀如实写出来。
        val core = FakeCore(listOf(legacyCore(1, clearEcho = false)))
        val result = CoreDenylistPush.drive(listOf(listOf("a.example"), listOf("b.example")), 2, core::send)
        assertEquals(CoreDenylistOutcome.NotPublished, result.outcome)
        assertTrue(result.detail.startsWith("core_lacks_clear_parameter@0"))
        assertTrue(result.detail.contains("保留已推送前缀 1 条"))
        assertEquals(1, core.received.size)
    }

    @Test
    fun partialAcceptIsItsOwnOutcomeNeverPublished() {
        val core = FakeCore(listOf(newCore(1)))
        val result = CoreDenylistPush.drive(listOf(listOf("ok.example", "bad host")), 2, core::send)
        assertEquals(CoreDenylistOutcome.PartialAccept, result.outcome)
        assertTrue(result.detail.contains("denylist_partial_accept accepted=1 input=2"))
    }

    @Test
    fun firstBatchRejectionIsNotPublishedWithZeroAccepted() {
        val core = FakeCore(emptyList(), failAt = 0)
        val result = CoreDenylistPush.drive(listOf(listOf("a.example"), listOf("b.example")), 2, core::send)
        assertEquals(CoreDenylistOutcome.NotPublished, result.outcome)
        assertEquals(0, result.accepted)
        assertTrue(result.detail.contains("首批被拒"))
        assertEquals(1, core.received.size)
    }

    @Test
    fun noBatchAtAllIsDistinguishableFromAnEmptyList() {
        val core = FakeCore(emptyList())
        val result = CoreDenylistPush.drive(emptyList(), 0, core::send)
        assertEquals("denylist_no_batch", result.detail)
        assertEquals(CoreDenylistOutcome.NotPublished, result.outcome)
        assertTrue(core.received.isEmpty())
    }

    @Test
    fun ackParsingFallsBackToLocalInputAndReadsCapabilityFromFields() {
        val parsed = CoreDenylistPush.parseAck("""{"decision":"ok","accepted":3,"staged":true}""", 5)
        assertTrue(parsed.published)
        assertEquals(3, parsed.accepted)
        // 核心没回 input ⇒ 退回本地 offered 数，绝不虚报成功
        assertEquals(5, parsed.input)
        assertTrue(parsed.echoesMode.not())
        assertTrue(parsed.echoesClear.not())
        assertTrue(parsed.staged)
    }

    @Test
    fun denyAckCarriesTheCoreReasonCode() {
        val parsed =
            CoreDenylistPush.parseAck(
                """{"decision":"deny","reason":{"code":"denylist_mode_invalid","detail":"x","explanation":""}}""",
                2,
            )
        assertTrue(parsed.published.not())
        assertEquals("denylist_mode_invalid", parsed.detail)
        assertEquals(2, parsed.input)
    }

    private fun newCore(
        accepted: Int,
        staged: Boolean = false,
    ) = CoreDenylistPush.Ack(true, accepted, accepted, true, true, staged, "ok")

    /** 3 参旧核心：回显 `clear` 但不回显 `mode`（`clearEcho=false` 即 2 参旧核心）。 */
    private fun legacyCore(
        accepted: Int,
        clearEcho: Boolean,
    ) = CoreDenylistPush.Ack(true, accepted, accepted, clearEcho, false, false, "legacy")

    private companion object {
        private val REFUSED = CoreDenylistPush.Ack(false, 0, 0, false, false, false, "ffi_input_too_long")
    }
}

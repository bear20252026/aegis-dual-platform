package com.aegis.broker

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path

/**
 * 内置/外部威胁名单文本的解析与切批（R9-B95）。
 *
 * 用例表是从 Windows `Core/Security/ThreatFeed.cs:ParseFeedLine` 的**分支**逐条推出来的
 * （不是随手造的样本）：那条链上有注释、`||`/`^`、协议、路径、端口、大小写、必须含点、
 * 字符白名单、长度这几刀，Android 少对齐任何一刀，两端就会对同一份源解析出不同集合，
 * 而「两端同口径」正是 Q51 的验收条件。三端解析器无共享向量这件事按 Q71 登记在册。
 */
class ThreatHostFeedTest {
    @Test
    fun commentsAndBlanksAreNotEntries() {
        val parsed = ThreatHostFeed.parse("# 注释\n\n! 元数据\n  \nbad.example\n")
        assertEquals(listOf("bad.example"), parsed.hosts)
        assertTrue("注释与空行不得计成被拒条目", parsed.rejected.isEmpty())
    }

    @Test
    fun adBlockDecorationsAreStrippedBeforeShapeCheck() {
        assertEquals("tracker.example", ThreatHostFeed.parseLine("||tracker.example^"))
        assertEquals("ads.example", ThreatHostFeed.parseLine("https://ads.example/path?x=1"))
        assertEquals("api.example", ThreatHostFeed.parseLine("||api.example:8443^"))
        assertEquals("mixed.example", ThreatHostFeed.parseLine("||MIXED.Example^"))
    }

    @Test
    fun malformedCandidatesAreRejectedAndNeverSilentlyDropped() {
        val messy = listOf("good.example", "not a host", "../etc", ".dot.example", "trailing.dot.", "double..dot")
        val parsed = ThreatHostFeed.parse(messy.joinToString(separator = "\n"))
        assertEquals(listOf("good.example"), parsed.hosts)
        val expected = listOf("../etc", ".dot.example", "double..dot", "not a host", "trailing.dot.")
        assertEquals(expected, parsed.rejected.sorted())
    }

    @Test
    fun localhostIsTheOneEntryAllowedWithoutADot() {
        assertEquals("localhost", ThreatHostFeed.parseLine("localhost"))
        assertNull(ThreatHostFeed.parseLine("intranet"))
    }

    @Test
    fun entryLengthCapMatchesTheCoreShapeRule() {
        val half = ThreatHostFeed.MAX_ENTRY_BYTES / 2
        val atCap = "a".repeat(half) + "." + "b".repeat(half - 1)
        assertTrue("恰好在上限内的 host 应当收下", ThreatHostFeed.entryShapeOk(atCap))
        val tooLong = atCap + "x"
        assertFalse(ThreatHostFeed.entryShapeOk(tooLong))
        assertNull(ThreatHostFeed.parseLine(tooLong))
    }

    @Test
    fun hostsAreDedupedAndSortedForAReproducibleBatchPlan() {
        val parsed = ThreatHostFeed.parse("b.example\na.example\nb.example\nA.example\n")
        assertEquals(listOf("a.example", "b.example"), parsed.hosts)
    }

    @Test
    fun emptyListStillProducesOneBatchSoTheChainReportsPublishedZero() {
        // 空清单出 0 批会被判成 NotPublished(denylist_no_batch)——那是「链断了」的形态，
        // 而内置名单今天就是空的，两态必须能分辨。
        val plan = ThreatHostFeed.batches(emptyList())
        assertEquals(1, plan.size)
        assertTrue(plan.single().isEmpty())
        assertEquals("[]", ThreatHostFeed.encode(emptyList()))
    }

    @Test
    fun encodeNeverProducesAnEmptyStringElement() {
        val hosts = listOf("a.example", "b.example")
        assertEquals("[\"a.example\",\"b.example\"]", ThreatHostFeed.encode(hosts))
    }

    @Test
    fun encodeEscapesTheCharactersThatWouldBreakTheWholeBatch() {
        // 这一条故意绕过 parse()：`AndroidBroker.updateThreatHostDenylist` 的调用方可以直接
        // 递任意字符串，而核心对**非良构 JSON 是整批拒收**——一个没转义的引号会把同批
        // 所有合法条目一起带走。判据用 JSON 解码器读回，不是比字符串形状。
        val hosts = listOf("a\"b.example", "c\\d.example", "范围.example", "tab\there.example")
        val decoded = JSONArray(ThreatHostFeed.encode(hosts))
        assertEquals(hosts.size, decoded.length())
        for (index in hosts.indices) {
            assertEquals(hosts[index], decoded.getString(index))
        }
    }

    @Test
    fun batchCapsAreCountedInUtf8BytesBecauseTheCoreCapsBytes() {
        // 多字节字符与控制符转义让「字符数」与「字节数」分开：按 char 断言等于没断言，
        // 因为核心那一刀（MAX_BATCH_BYTES）量的是 UTF-8 字节。
        val hosts = List(NASTY_COUNT) { index -> "误$index.example\u0001\u0002" }
        val plan = ThreatHostFeed.batches(hosts)
        assertTrue("多字节名单应切成多批", plan.size > 1)
        for (batch in plan) {
            val bytes = ThreatHostFeed.encode(batch).toByteArray(Charsets.UTF_8).size
            val overTheCap = bytes > ThreatHostFeed.MAX_BATCH_BYTES
            assertFalse("一批载荷 $bytes 字节越过核心上限 ${ThreatHostFeed.MAX_BATCH_BYTES}", overTheCap)
        }
        assertEquals(hosts.size, plan.sumOf { it.size })
    }

    @Test
    fun batchesStayUnderTheCorePayloadCapAndCoverEveryHostOnce() {
        val hosts = List(HOST_COUNT) { index -> "host$index.example" }
        val plan = ThreatHostFeed.batches(hosts)
        assertTrue("单份名单应切成多批", plan.size > 1)
        for (batch in plan) {
            val bytes = ThreatHostFeed.encode(batch).toByteArray(Charsets.UTF_8).size
            assertTrue("一批载荷 $bytes 超过预算", bytes <= ThreatHostFeed.CHUNK_PAYLOAD_BYTES)
        }
        assertEquals(hosts.size, plan.sumOf { it.size })
        assertEquals(hosts.toSet(), plan.flatten().toSet())
    }

    @Test
    fun aSingleSmallListIsOneBatchAndNeedsNoSession() {
        assertEquals(1, ThreatHostFeed.batches(listOf("one.example", "two.example")).size)
    }

    // ---------- R9-B96（队列 Q71）：跨端共享向量消费 ----------

    @Test
    fun sharedFeedLineVectorParsesToTheSameVerdictOnBothEnds() {
        // 这份向量判的是「同一行文本在两端给出同一个结论」——Android 侧本批此前只有
        // 从 C# 分支表推出来的手写用例，那份表能守住 Android 自己，守不住两端的漂移。
        val vectors = loadSharedVectors(VECTOR_FILE)
        assertTrue("向量条目数塌缩（${vectors.length()} 条）", vectors.length() >= MIN_VECTOR_ITEMS)
        for (index in 0 until vectors.length()) {
            assertOneVector(vectors.getJSONObject(index))
        }
    }

    /** 单条向量的三态判定：`valid` 必须带 `host` 并逐字符相等，`deny` 必须不带 `host` 且解析为空。 */
    private fun assertOneVector(item: JSONObject) {
        val line = item.getString("line")
        val expected = item.getString("expected")
        val host = ThreatHostFeed.parseLine(line)
        if (expected == "valid") {
            // 配对判据不是洁癖：把 host 字段从 valid 条目上删掉，断言会退化成「解析出点什么就行」
            assertTrue("valid 条目必须带 host 字段：$line", item.has("host"))
            assertEquals("Android 与共享向量不一致：$line", item.getString("host"), host)
        } else if (expected == "deny") {
            assertFalse("deny 条目不得带 host 字段：$line", item.has("host"))
            assertNull("Android 与共享向量不一致（本行不该产出条目）：$line", host)
        } else {
            throw AssertionError("向量里出现本文件没有定义的 expected=$expected：$line")
        }
    }

    /** 仓库根 `contracts/vectors` 相对定位（与 `OriginPolicyTest.loadSharedVectors` 同一形状）。 */
    private fun loadSharedVectors(fileName: String): JSONArray {
        val path =
            generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
                .take(8)
                .map { it.resolve("contracts").resolve("vectors").resolve(fileName) }
                .firstOrNull { Files.isRegularFile(it) }
                ?: error("找不到共享向量 $fileName（相对仓库根定位失败）")
        return JSONObject(String(Files.readAllBytes(path), Charsets.UTF_8)).getJSONArray("vectors")
    }

    private companion object {
        const val HOST_COUNT = 9_000
        const val NASTY_COUNT = 4_000
        const val VECTOR_FILE = "threat-feed-line.json"
        const val MIN_VECTOR_ITEMS = 30
    }
}

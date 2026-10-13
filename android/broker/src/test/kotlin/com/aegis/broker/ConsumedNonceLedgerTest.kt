package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * R9-AD-5（第九轮队列 Q5）：已消费 nonce 的账本键必须**会话作用域**，否则
 * `destroySession` 的回收判据（按 `sessionId:` 前缀摘）对原生形态一条都摘不掉。
 *
 * 为什么这里的判据是「纯函数 + 源码接线」而不是「端到端跑一次原生消费」：
 * 原生分支要 `BuildConfig.REQUIRE_NATIVE_POLICY_CORE` 且真实 `.so`，JVM 单测里到不了
 * （Windows 侧同一限制见 `BrowserPolicyBroker.NativeNonceLedger.cs` 的 R8-CS-REG-01
 * 注记——那里的教训是「文本锚证明不了数学」，所以键推导被抽成纯函数单独断言）。
 * 本文件因此两头都钉：键的数学（1–4）＋两个写入点确实走这个键（5）。
 */
class ConsumedNonceLedgerTest {
    // 核心返回的裸 hex 形态（64 位十六进制，无 sessionId 前缀）。
    private val bareNativeNonce = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    @Test
    fun nativeShapedNonceKeyIsRetirableByItsSession() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("s-native", "tab-1"))
        // 写入侧与生产路径同用 nonceLedgerKey；回收侧走 destroySession 的真实实现。
        broker.consumedNonces.add(nonceLedgerKey("s-native", bareNativeNonce))
        broker.destroySession("s-native")
        assertFalse(
            "启用原生核心时关标签必须摘掉该会话的账本条目",
            broker.consumedNonces.any { it.contains(bareNativeNonce) },
        )
    }

    @Test
    fun bareNonceWithoutLedgerKeyIsTheDefectShape() {
        // 反向锚：旧写入形态（裸 nonce 入账）在 destroySession 后仍在册——
        // 这条断言为真才说明上面那条测试真的在判「键形态」，而不是恒绿。
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("s-old", "tab-1"))
        broker.consumedNonces.add(bareNativeNonce)
        broker.destroySession("s-old")
        assertTrue(broker.consumedNonces.contains(bareNativeNonce))
        assertFalse(nonceLedgerPrefix("s-old") in bareNativeNonce)
    }

    @Test
    fun managedNonceKeyStaysUnprefixedTwiceOver() {
        // 托管 nonce 本身已带 `sessionId:` 前缀 ⇒ 折算必须幂等（不叠第二层前缀）。
        val sessionId = "s-mixed"
        val managed = AndroidBroker.newNonce(sessionId)
        assertTrue(managed.startsWith(nonceLedgerPrefix(sessionId)))
        assertEquals(managed, nonceLedgerKey(sessionId, managed))
        assertEquals("$sessionId:$bareNativeNonce", nonceLedgerKey(sessionId, bareNativeNonce))
    }

    @Test
    fun ledgerEntriesDoNotCrossSessions() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("s1", "tab-1"))
        assertTrue(broker.registerSession("s12", "tab-2"))
        broker.consumedNonces.add(nonceLedgerKey("s1", bareNativeNonce))
        broker.consumedNonces.add(nonceLedgerKey("s12", bareNativeNonce))
        broker.destroySession("s1")
        // 前缀带冒号 ⇒ "s1" 的回收不得顺手摘掉 "s12" 的同名 nonce 条目。
        assertEquals(1, broker.consumedNonces.size)
        assertTrue(broker.consumedNonces.all { it.belongsToNonceLedger("s12") })
        assertFalse(broker.consumedNonces.any { it.belongsToNonceLedger("s1") })
    }

    @Test
    fun bothWritePathsGoThroughTheLedgerKey() {
        // 接线锚：托管与原生两条写入路径都必须经 nonceLedgerKey 入账，回收侧必须用
        // belongsToNonceLedger——两侧共用一个前缀约定，才不会再各抄一份而失配。
        val source = File(System.getProperty("user.dir"), "src/main/kotlin/com/aegis/broker/AndroidBroker.kt")
        assertTrue("用例 working dir 不对，读不到被测源文件：${source.absolutePath}", source.isFile)
        val text = source.readText()
        assertEquals(
            "两个消费点都要经 nonceLedgerKey 折算",
            2,
            Regex("trackConsumedNonce\\(nonceLedgerKey\\(").findAll(text).count(),
        )
        assertTrue(text.contains("removeIf { nonce -> nonce.belongsToNonceLedger(sessionId) }"))
        // 入账参数必须是「账本键」而不是裸 nonce——名字变了就说明写入侧只剩一条通道。
        assertTrue(text.contains("private fun trackConsumedNonce(ledgerKey: String): Boolean {"))
        assertTrue(text.contains("consumedNonces.add(ledgerKey)"))
        assertFalse(
            "回收侧不得退回按字面前缀硬拆的旧形态（键与判据必须同源于 nonceLedgerPrefix）",
            text.contains("nonce.startsWith(\"\$sessionId:\")"),
        )
    }
}

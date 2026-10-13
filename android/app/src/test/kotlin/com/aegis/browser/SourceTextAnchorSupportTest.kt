package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * R9-SH-16：按文本判定源码的常驻用例，必须先在**剔过注释**的源面上匹配。
 *
 * 两个模块（`:broker` / `:app`）各有一份 `withoutComments()`——跨模块共享要动 Gradle 的
 * testFixtures 配置（构建面变更，不在按文本判定的批次里顺手做）。本文件在两个源集里是
 * **同一组语料、同一批断言**：任何一边改了口径，同一份语料在另一边就会给出不同答案，
 * 而这里的期望值是写死的——「两副本各漂各的」因此不可能悄悄发生。
 *
 * 每条语料都带一条**恒真防呆**（原文里必须含 token）——否则「剔完不含」在语料本身没造出
 * 场景时也会通过，正是 R9-SH-7 判过的那类假锚。
 */
class SourceTextAnchorSupportTest {
    private val token = "trackConsumedNonce(nonceLedgerKey("

    private val codeShapes =
        listOf(
            "        val ok = $token sessionId, nonce)",
            "    val list = listOf($token a, $token b)",
        )

    private val commentShapes =
        listOf(
            "    // 旧写法是 $token ，本批已改",
            "    /* 注记：$token 只是历史提及 */",
            "/* 说明" + "\n" + " * 历史写法 $token" + "\n" + " */",
            "    # 迁移说明：$token",
        )

    @Test
    fun codeLinesSurviveTheStrip() {
        for (line in codeShapes) {
            assertTrue("语料本身没含 token：$line", token in line)
            assertTrue("代码行被剔掉了：${line.withoutComments()}", token in line.withoutComments())
        }
    }

    @Test
    fun commentMentionsNeverCount() {
        for (line in commentShapes) {
            assertTrue("语料本身没含 token：$line", token in line)
            assertFalse("注释里的 token 还在：${line.withoutComments()}", token in line.withoutComments())
        }
    }

    @Test
    fun lineCommentHoldingAFakeBlockOpenDoesNotEatFollowingCode() {
        // 顺序判据（R9-B45 收敛时实测撞出来的那条）：整行注释里的 `"https://*"` 含一个
        // `/`+`*` 的假块起点。先做块匹配就会一路吃到下一个 `*/`，把中间的真语句一起删掉；
        // 先剔整行注释再匹配块，才是「判代码」而不是「判注释的形状」。
        val corpus =
            "        // allowedOriginRules 不接受 \"https://*\" 这种全域通配" +
                "\n        val allowedOrigins = setOf(\"*\")" +
                "\n        // 下一个块收尾 */ 只是文本"
        assertTrue("语料本身没造出被吞的那一行", "val allowedOrigins" in corpus)
        assertTrue("行注释里的假块起点吞掉了后面的代码行", "val allowedOrigins" in corpus.withoutComments())
    }

    @Test
    fun strippingIsNotJustDeletingTheWholeText() {
        // 正面控制的另一面：剔完必须还剩东西——否则上面两条可以由「把整个输入清空」这一
        // 实现同时满足（恒绿的第三种形态）。
        val mixed = "    val a = $token s, n)" + "\n" + "    // $token 历史写法"
        val stripped = mixed.withoutComments()
        assertTrue(stripped.isNotBlank())
        assertTrue(stripped.contains("val a"))
    }
}

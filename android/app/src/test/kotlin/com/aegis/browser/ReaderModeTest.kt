package com.aegis.browser

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ReaderMode 两段解析 JVM 单测（2026-09-24 审计——AD-028）。
 * parse 是「页内脚本返回值」的信任边界——畸形返回不得崩溃、
 * ok=false/空正文不得进入阅读模式、超长正文必须截断。
 *
 * Robolectric（AD-322）：空标题兜底断言需资源解析
 * （R.string.reader_mode_title 与 MainDialogs.ReaderDialog 渲染同源）。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ReaderModeTest {
    /** 构建 payload JSON（非链式——ktlint chained-expression 规则）。 */
    private fun payload(
        ok: Boolean,
        title: String? = null,
        text: String? = null,
    ): String {
        val obj = JSONObject()
        obj.put("ok", ok)
        if (title != null) obj.put("title", title)
        if (text != null) obj.put("text", text)
        return obj.toString()
    }

    @Test
    fun nullAndBlankInputsReturnNull() {
        assertNull(ReaderMode.parse(null))
        assertNull(ReaderMode.parse(""))
        assertNull(ReaderMode.parse("   "))
    }

    @Test
    fun directJsonObjectPayloadParses() {
        val content = ReaderMode.parse(payload(ok = true, title = "标题", text = "正文内容"))
        assertEquals("标题", content!!.title)
        assertEquals("正文内容", content.text)
    }

    @Test
    fun twoLayerStringPayloadParses() {
        // evaluateJavascript 返回「含 JSON 的字符串」的 JSON 表示——先还原字符串再解析
        val inner = payload(ok = true, title = "标题", text = "正文")
        val content = ReaderMode.parse(JSONObject.quote(inner))
        assertEquals("标题", content!!.title)
        assertEquals("正文", content.text)
    }

    @Test
    fun okFalseYieldsNull() {
        assertNull(ReaderMode.parse(payload(ok = false)))
    }

    @Test
    fun blankTextYieldsNull() {
        assertNull(ReaderMode.parse(payload(ok = true, text = "   ")))
    }

    @Test
    fun blankTitleFallsBackToDefault() {
        // AD-322：空标题兜底迁 UI 层资源单源——数据层 parse 空标题原样透传
        // （不再硬编码中文）；ReaderDialog 渲染以 R.string.reader_mode_title
        // ifBlank 兜底。期望文本经资源解析与渲染同源，不硬编码。
        val app = ApplicationProvider.getApplicationContext<Application>()
        val content = ReaderMode.parse(payload(ok = true, text = "正文"))!!
        assertEquals("数据层空标题必须原样透传（兜底职责在 UI 层）", "", content.title)
        assertEquals(
            app.getString(R.string.reader_mode_title),
            content.title.ifBlank { app.getString(R.string.reader_mode_title) },
        )
    }

    @Test
    fun malformedPayloadReturnsNullInsteadOfThrowing() {
        assertNull(ReaderMode.parse("{not json"))
        assertNull(ReaderMode.parse("123"))
        assertNull(ReaderMode.parse("\"just a string\""))
    }

    @Test
    fun oversizedTextIsTruncated() {
        val longText = "a".repeat(300_000)
        assertEquals(200_000, ReaderMode.parse(payload(ok = true, text = longText))!!.text.length)
    }

    // AD-227（2026-09-26 审计）：超长标题此前无上限直进 AlertDialog 标题
    @Test
    fun oversizedTitleIsTruncated() {
        val longTitle = "标".repeat(1_000)
        assertEquals(256, ReaderMode.parse(payload(ok = true, title = longTitle, text = "正文"))!!.title.length)
    }

    // ---------------- AD-109/125（审计 2026-09-23 清单·A6 批） ----------------

    @Test
    fun truncationNeverSplitsSurrogatePairs() {
        // AD-109：String.take 按 UTF-16 char 劈切——切点落在增补字符中间
        // 会产生孤立代理对（渲染为替换符且 length 语义失真）。构造 emoji
        // 落在 200_000 切点上的正文（=MAX_TEXT-1 个 'a' + 2 char emoji）。
        val emoji = "\uD83D\uDE00"
        val text = "a".repeat(199_999) + emoji + "b"
        val content = ReaderMode.parse(payload(ok = true, text = text))!!
        assertEquals(199_999, content.text.length)
        assertFalse("截断结果不得以孤立高代理结尾", Character.isHighSurrogate(content.text.last()))
    }

    @Test
    fun takeAtCharBoundaryFallsBackBeforeDanglingSurrogate() {
        // 高代理落在切点尾 → 回退一个 char；ASCII 行为与 String.take 一致
        assertEquals(1, takeAtCharBoundary("a\uD83D\uDE00", 2).length)
        assertEquals("", takeAtCharBoundary("\uD83D\uDE00", 1))
        assertEquals("abc", takeAtCharBoundary("abcdef", 3))
        assertEquals("abcdef", takeAtCharBoundary("abcdef", 6))
    }

    @Test
    fun extractScriptKeepsMinTextThreshold() {
        // AD-125：MIN_TEXT 门槛在页内脚本生效（parse 只看 ok 标记）——
        // 锁定脚本内嵌阈值 200，防误删/漂移
        assertTrue("提取脚本必须内嵌 MIN_TEXT=200 门槛", ReaderMode.EXTRACT_JS.contains("length >= 200"))
    }

    // ---------------- AD-206（审计 2026-09-23 清单·A7 批）：候选扫描设限 ----------------

    @Test
    fun extractScriptCapsCandidateScan() {
        // 候选块全量遍历（数千 div 逐个 innerText）会强制布局抖动——脚本必须
        // 内嵌候选上限，超限节点不参与正文评选
        assertTrue(
            "提取脚本必须内嵌候选上限 MAX_CANDIDATES",
            ReaderMode.EXTRACT_JS.contains("MAX_CANDIDATES = 400"),
        )
        assertTrue(
            "扫描必须按上限截断（n = min(cand.length, MAX_CANDIDATES)）",
            ReaderMode.EXTRACT_JS.contains("var n = cand.length < MAX_CANDIDATES"),
        )
    }

    @Test
    fun extractScriptExitsEarlyOnSufficientBody() {
        // 提前退出：正文量已达 MAX_TEXT 的候选即最优，后续候选不得再扫描
        assertTrue(
            "必须内嵌「正文达标即停止扫描」的 break",
            ReaderMode.EXTRACT_JS.contains("if (bestLen >= 200000) { break; }"),
        )
    }
}

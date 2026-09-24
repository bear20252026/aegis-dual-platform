package com.aegis.browser

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * ReaderMode 两段解析 JVM 单测（2026-09-24 审计——AD-028）。
 * parse 是「页内脚本返回值」的信任边界——畸形返回不得崩溃、
 * ok=false/空正文不得进入阅读模式、超长正文必须截断。
 */
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
        assertEquals("阅读模式", ReaderMode.parse(payload(ok = true, text = "正文"))!!.title)
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
}

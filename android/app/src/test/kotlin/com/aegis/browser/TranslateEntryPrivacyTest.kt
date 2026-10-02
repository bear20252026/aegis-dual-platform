package com.aegis.browser

import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * AD-280（2026-10-01 审计）：翻译 URL 外发的 fragment 剥离——fragment 是
 * OAuth Authorization Code / session token 的唯一载体（#access_token=…），
 * 整页外发翻译服务即凭据泄漏面。Robolectric 供 android.net.Uri.encode 真实
 * 实现（returnDefaultValues 桩下 encode 返回 null，无法做内容级断言）。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TranslateEntryPrivacyTest {
    @Test
    fun fragmentIsStrippedBeforeEncoding() {
        val pageUrl = "https://a.gov.cn/page?code=1#access_token=secret_token"
        val url = TranslateEntry.buildUrl(pageUrl)
        assertNotNull(url)
        assertFalse("fragment（token 载体）不得外发翻译服务", url!!.contains("secret_token"))
        assertFalse(url.contains("access_token"))
        // AD-313（2026-10-02 审计）：敏感 query 参数（code）同步剥离——
        // 编码目标为剥 fragment + 剥敏感参数后的 URL
        val expected = Uri.encode("https://a.gov.cn/page")
        assertTrue("a= 参数必须是剥 fragment/敏感参数后的编码 URL", url.contains("a=$expected"))
    }

    // ---------------- AD-313（2026-10-02 审计）：敏感 query 参数剥离 ----------------

    @Test
    fun sensitiveQueryParamsAreStrippedBeforeSending() {
        // OAuth Code/State 与 token 实际经 query 流转（非仅 fragment）——
        // 外发翻译服务前必须剥离（名称大小写不敏感）
        assertFalse(TranslateEntry.buildUrl("https://a.gov.cn/cb?code=AUTHCODE&state=s1")!!.contains("AUTHCODE"))
        assertFalse(TranslateEntry.buildUrl("https://a.gov.cn/cb?code=AUTHCODE&state=s1")!!.contains("state=s1"))
        assertFalse(TranslateEntry.buildUrl("https://a.gov.cn/cb?token=TOKEN123")!!.contains("TOKEN123"))
        assertFalse(TranslateEntry.buildUrl("https://a.gov.cn/cb?CODE=UPPER")!!.contains("UPPER"))
        // 非敏感参数保留（翻译服务取页可能依赖）
        val kept = TranslateEntry.buildUrl("https://a.gov.cn/page?code=1&keep=me")!!
        assertTrue("非敏感参数必须保留", kept.contains(Uri.encode("https://a.gov.cn/page?keep=me")))
    }

    @Test
    fun stripSensitiveQueryParamsPureFunctionSemantics() {
        // 纯函数直测：无命中原样返回；全量剥空移除 '?'
        assertEquals(
            "https://a.gov.cn/plain?x=1",
            TranslateEntry.stripSensitiveQueryParams("https://a.gov.cn/plain?x=1"),
        )
        assertEquals(
            "https://a.gov.cn/cb",
            TranslateEntry.stripSensitiveQueryParams("https://a.gov.cn/cb?code=1"),
        )
        assertEquals(
            "https://a.gov.cn/no-query",
            TranslateEntry.stripSensitiveQueryParams("https://a.gov.cn/no-query"),
        )
    }

    @Test
    fun fragmentlessUrlsAreUnchangedByStripping() {
        val url = TranslateEntry.buildUrl("https://a.gov.cn/plain")!!
        val expected = Uri.encode("https://a.gov.cn/plain")
        assertTrue(url.contains("a=$expected"))
    }
}

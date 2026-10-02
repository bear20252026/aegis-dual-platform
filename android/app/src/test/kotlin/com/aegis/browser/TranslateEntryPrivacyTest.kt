package com.aegis.browser

import android.net.Uri
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
        // 编码目标精确为剥除 fragment 后的 URL（path/query 保留——翻译取页依赖）
        val expected = Uri.encode("https://a.gov.cn/page?code=1")
        assertTrue("a= 参数必须是剥 fragment 后的编码 URL", url.contains("a=$expected"))
    }

    @Test
    fun fragmentlessUrlsAreUnchangedByStripping() {
        val url = TranslateEntry.buildUrl("https://a.gov.cn/plain")!!
        val expected = Uri.encode("https://a.gov.cn/plain")
        assertTrue(url.contains("a=$expected"))
    }
}

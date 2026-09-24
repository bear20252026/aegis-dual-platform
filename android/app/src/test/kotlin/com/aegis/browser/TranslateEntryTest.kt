package com.aegis.browser

import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * TranslateEntry.buildUrl JVM 单测（2026-09-24 审计——AD-029）。
 * 非 http(s) 页面必须拒绝（本地壳页/about: 不外发翻译服务——隐私边界）。
 * 注：正例的参数值经 android.net.Uri.encode（JVM 默认值兜底）——精确
 * 断言锁定前缀与 a= 参数存在性，完整编码由真机走查覆盖。
 */
class TranslateEntryTest {
    @Test
    fun nullAndBlankPageUrlsAreRejected() {
        assertNull(TranslateEntry.buildUrl(null))
        assertNull(TranslateEntry.buildUrl(""))
        assertNull(TranslateEntry.buildUrl("   "))
    }

    @Test
    fun nonHttpSchemesAreRejected() {
        assertNull(TranslateEntry.buildUrl("file:///android_asset/start.html"))
        assertNull(TranslateEntry.buildUrl("about:blank"))
        assertNull(TranslateEntry.buildUrl("javascript:void(0)"))
        assertNull(TranslateEntry.buildUrl("data:text/html,x"))
    }

    @Test
    fun httpAndHttpsPagesProduceServiceUrl() {
        val prefix = "https://www.translatetheweb.com/?from=auto&to=zh-Hans&a="
        assertTrue(TranslateEntry.buildUrl("https://a.gov.cn/page?x=1")!!.startsWith(prefix))
        assertTrue(TranslateEntry.buildUrl("http://intranet.example/")!!.startsWith(prefix))
    }
}

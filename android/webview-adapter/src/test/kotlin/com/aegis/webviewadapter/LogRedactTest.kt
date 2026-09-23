package com.aegis.webviewadapter

import org.junit.Assert.assertEquals
import org.junit.Test

/** LogRedact 行为级单测（AD-004 配套——webview-adapter 模块首批 JVM 测试）。 */
class LogRedactTest {
    @Test
    fun stripsQueryAndFragment() {
        assertEquals("https://a.gov.cn/path…", LogRedact.redact("https://a.gov.cn/path?token=secret&q=x#anchor"))
        assertEquals("https://a.gov.cn/path…", LogRedact.redact("https://a.gov.cn/path?token=secret"))
        assertEquals("https://a.gov.cn/path…", LogRedact.redact("https://a.gov.cn/path#anchor"))
    }

    @Test
    fun plainUrlAppendsEllipsisOnly() {
        assertEquals("https://a.gov.cn…", LogRedact.redact("https://a.gov.cn"))
    }

    @Test
    fun nullAndEmptyHandled() {
        assertEquals("<null>", LogRedact.redact(null))
        assertEquals("<null>", LogRedact.redact(""))
    }
}

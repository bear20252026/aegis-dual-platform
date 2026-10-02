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

    // ---------------- AD-264（2026-10-01 审计）：userinfo 剥除 ----------------

    @Test
    fun userinfoIsStrippedBeforeQueryTruncation() {
        // token@host 形态脱敏后凭据不得残留（token 常为 OAuth/会话凭据载体）
        assertEquals("https://***@host.example/path…", LogRedact.redact("https://token@host.example/path?q=1"))
        assertEquals("https://***@host.example/path…", LogRedact.redact("https://user:pass@host.example/path#frag"))
        assertEquals("https://***@host.example:8443/…", LogRedact.redact("https://secret@host.example:8443/?t=1"))
    }

    @Test
    fun urlsWithoutUserInfoAreUnaffectedByStripping() {
        // authority 段外的 @（query/fragment 中）不影响脱敏形态
        assertEquals("https://host.example/p…", LogRedact.redact("https://host.example/p?mail=a@b.example"))
    }
}

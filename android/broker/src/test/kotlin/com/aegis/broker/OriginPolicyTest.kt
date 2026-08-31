package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * A-3 回归（架构审计 2026-08-31）：OriginPolicy 与 Rust origin.rs /
 * Python security.py 的跨端语义对齐——userinfo/控制字符/非法端口/超长
 * 全部 fail-closed，host 大小写不敏感。
 */
class OriginPolicyTest {
    @Test
    fun `valid http and https urls parse`() {
        assertNotNull(OriginPolicy.tryParseExternal("https://example.com/path?x=1"))
        assertNotNull(OriginPolicy.tryParseExternal("http://example.com"))
    }

    @Test
    fun `userinfo is rejected`() {
        assertNull(OriginPolicy.tryParseExternal("https://user@evil.com"))
        assertNull(OriginPolicy.tryParseExternal("https://user:pass@evil.com"))
    }

    @Test
    fun `control characters and whitespace are rejected`() {
        assertNull(OriginPolicy.tryParseExternal("https://evil.com/\u0000x"))
        assertNull(OriginPolicy.tryParseExternal("https://evil.com/ x"))
        assertNull(OriginPolicy.tryParseExternal("https://evil.com/\u007f"))
    }

    @Test
    fun `non http schemes are rejected`() {
        assertNull(OriginPolicy.tryParseExternal("file:///etc/passwd"))
        assertNull(OriginPolicy.tryParseExternal("javascript:alert(1)"))
        assertNull(OriginPolicy.tryParseExternal("data:text/html,x"))
        assertNull(OriginPolicy.tryParseExternal("blob:https://example.com/x"))
    }

    @Test
    fun `oversized url is rejected`() {
        val long = "https://example.com/" + "a".repeat(9000)
        assertNull(OriginPolicy.tryParseExternal(long))
    }

    @Test
    fun `port out of range is rejected`() {
        assertNull(OriginPolicy.tryParseExternal("https://example.com:99999"))
    }

    @Test
    fun `valid port is accepted`() {
        val uri = OriginPolicy.tryParseExternal("https://example.com:8443/x")
        assertNotNull(uri)
        assertEquals(8443, uri?.port)
    }
}

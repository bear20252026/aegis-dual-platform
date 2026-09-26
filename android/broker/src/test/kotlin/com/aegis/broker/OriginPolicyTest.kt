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

    @Test
    fun `exact about blank is allowed (T2 regression)`() {
        // T2 修复（全面审计批次2）：归一层放行 about:blank 而决策层必拒的
        // 自相矛盾死路径——现在精确 about:blank 放行
        assertNotNull(OriginPolicy.tryParseExternal("about:blank"))
        assertNotNull(OriginPolicy.tryParseExternal("ABOUT:BLANK"))
        assertNotNull(OriginPolicy.tryParseExternal("  about:blank  "))
    }

    @Test
    fun `other about variants stay rejected`() {
        // 只放行精确 about:blank——about:evil/about:config 等仍 fail-closed
        assertNull(OriginPolicy.tryParseExternal("about:evil"))
        assertNull(OriginPolicy.tryParseExternal("about:config"))
        assertNull(OriginPolicy.tryParseExternal("about:blank/extra"))
    }

    // ---------------- AD-213（2026-09-26 审计）：IPv4 备用编码两类漏判 ----------------

    @Test
    fun `leading zero octal ipv4 is rejected`() {
        // 四段全数字 + 前导零：inet_aton 系解析栈按八进制解释（0177.0.0.1 =
        // 127.0.0.1）——此前「4 段全数字即放行」漏判
        assertNull(OriginPolicy.tryParseExternal("https://0177.0.0.1/"))
        assertNull(OriginPolicy.tryParseExternal("https://010.0.0.138/"))
        assertNull(OriginPolicy.tryParseExternal("https://example.01.com/"))
    }

    @Test
    fun `hex segment ipv4 variants are rejected`() {
        // 0x 逐段判定：`0x7f.1`（整串 startsWith("0x") 因含 `.` 漏判）与
        // 混合形态统一拒绝；整串 0x 形态保持拒绝（回归）
        assertNull(OriginPolicy.tryParseExternal("https://0x7f.1/"))
        assertNull(OriginPolicy.tryParseExternal("https://0x7f.0.0.1/"))
        assertNull(OriginPolicy.tryParseExternal("https://0x7f000001/"))
        assertNull(OriginPolicy.tryParseExternal("https://1.0x7f.0.1/"))
    }

    @Test
    fun `dotted decimal ipv4 loopback stays accepted`() {
        // 点分十进制 127.0.0.1 必须保持放行（bridge_guard 白名单依赖——
        // 「0」单字符段非前导零形态）
        assertNotNull(OriginPolicy.tryParseExternal("https://127.0.0.1/"))
        assertNotNull(OriginPolicy.tryParseExternal("https://192.168.0.10/"))
    }
}

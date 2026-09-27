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

    // ---------- AD-120（审计 2026-09-23 清单·A6 批）：大写解析 ----------

    @Test
    fun `uppercase schemes parse case-insensitively`() {
        // scheme 大小写不敏感（java.net.URI 归一小写）——大写 https 必须放行
        assertNotNull(OriginPolicy.tryParseExternal("HTTPS://Example.COM/x"))
        assertNotNull(OriginPolicy.tryParseExternal("Http://example.com"))
    }

    @Test
    fun `uppercase about blank is allowed`() {
        // about:blank 精确匹配（大小写不敏感）；其他 about 变体仍拒绝
        assertNotNull(OriginPolicy.tryParseExternal("ABOUT:BLANK"))
        assertNotNull(OriginPolicy.tryParseExternal("About:Blank"))
        assertNull(OriginPolicy.tryParseExternal("ABOUT:EVIL"))
    }

    @Test
    fun `uppercase host is preserved for later canonicalization`() {
        // 解析层不吞大写 host（host 小写化是 canonicalize 的职责——分层不变）
        val uri = OriginPolicy.tryParseExternal("https://EXAMPLE.COM/x")
        assertNotNull(uri)
        assertEquals("EXAMPLE.COM", uri!!.host)
    }

    // ---------- AD-168（审计 2026-09-23 清单·A7 批）：控制字符/空白全集逐项 ----------

    @Test
    fun `every c0 control char and del is rejected item by item`() {
        // isControlChar 全集逐项：C0（0x00..0x1F）+ DEL（0x7F）——任一出现即拒绝
        // （userinfo 注入与 URL 拆分混淆面 fail-closed）
        for (code in 0x00..0x1F) {
            val ch = code.toChar()
            assertNull(
                "C0 控制字符 0x%02X 必须拒绝".format(code),
                OriginPolicy.tryParseExternal("https://example.com/${ch}x"),
            )
        }
        assertNull(
            "DEL 0x7F 必须拒绝",
            OriginPolicy.tryParseExternal("https://example.com/\u007Fx"),
        )
    }

    @Test
    fun `every kotlin whitespace char is rejected item by item`() {
        // Char.isWhitespace 全集逐项采样：含 C0 空白、unicode 空白分隔符
        // （全角空格/表意空格/NER/LS/PS 等）。NBSP(0x00A0) 不在
        // Character.isWhitespace 集——其拒绝路径由 URI 语法层兜底，不在
        // 本断言范围（isControlChar 的契约面只覆盖 isWhitespace 真值）。
        val samples =
            listOf(
                '\u0009', // HORIZONTAL TABULATION
                '\u000A', // LINE FEED
                '\u000B', // VERTICAL TABULATION
                '\u000C', // FORM FEED
                '\u000D', // CARRIAGE RETURN
                '\u001C', // FILE SEPARATOR
                '\u001D', // GROUP SEPARATOR
                '\u001E', // RECORD SEPARATOR
                '\u001F', // UNIT SEPARATOR
                ' ', // SPACE
                '\u0085', // NEXT LINE
                '\u1680', // OGHAM SPACE MARK
                '\u2000', // EN QUAD
                '\u2028', // LINE SEPARATOR
                '\u2029', // PARAGRAPH SEPARATOR
                '\u202F', // NARROW NO-BREAK SPACE（isWhitespace=true）
                '\u3000', // IDEOGRAPHIC SPACE
            )
        samples.forEach { ch ->
            assertNull(
                "空白字符 U+%04X 必须拒绝".format(ch.code),
                OriginPolicy.tryParseExternal("https://evil.com/${ch}x"),
            )
        }
        // 空白注入在 authority 段同样 fail-closed（拆分混淆主战场）
        assertNull(OriginPolicy.tryParseExternal("https://evil.com\u2028/"))
    }

    // ---------- AD-169（审计 2026-09-23 清单·A7 批）：端口 65535/65536 边界 ----------

    @Test
    fun `port 65535 boundary is accepted`() {
        // TCP 端口上限（RFC 6335）恰好等于上限 → 放行
        val uri = OriginPolicy.tryParseExternal("https://example.com:65535/")
        assertNotNull(uri)
        assertEquals(65535, uri!!.port)
    }

    @Test
    fun `port 65536 boundary is rejected`() {
        // 上限 + 1 → fail-closed（此前只测了 99999，65536 精确边界缺失）
        assertNull(OriginPolicy.tryParseExternal("https://example.com:65536/"))
    }
}

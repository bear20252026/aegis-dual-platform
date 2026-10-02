package com.aegis.broker

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path

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

    // ---------- AD-252（P1，2026-10-01 审计）+ AD-274：尾点 host 拒绝 ----------

    @Test
    fun `trailing dot hostnames are rejected`() {
        // 尾点 host：java.net.URI 保留尾点放行，Chromium 归一剥尾点后命中
        // bridge_guard 白名单成 trustedCaller——必须整链 fail-closed。
        // 回归锚点向量与审计台账一致（含带端口形态）。
        assertNull(OriginPolicy.tryParseExternal("https://localhost./"))
        assertNull(OriginPolicy.tryParseExternal("https://aegis.local./"))
        assertNull(OriginPolicy.tryParseExternal("https://example.com.:8443/"))
        assertNull(OriginPolicy.tryParseExternal("http://127.0.0.1./"))
    }

    // ---------- AD-299（P2，2026-10-02 审计）：host 校验对齐 Rust origin.rs ----------

    @Test
    fun `charset whitelist rejects unsafe host characters`() {
        // PY-074：下划线/引号不在 DNS 安全字符集 [a-z0-9.-]
        assertNull(OriginPolicy.tryParseExternal("https://exa_mple.org/"))
        assertNull(OriginPolicy.tryParseExternal("https://exa\"mple.org/"))
        // 对照：punycode（xn--）与普通域放行
        assertNotNull(OriginPolicy.tryParseExternal("https://xn--e1afmkfd.xn--p1ai/"))
    }

    @Test
    fun `leading dot and empty labels are rejected`() {
        // PY-073：前导点（空首标签）/ 连续点（空标签）拒绝
        assertNull(OriginPolicy.tryParseExternal("https://.example.org/"))
        assertNull(OriginPolicy.tryParseExternal("https://a..example.org/"))
    }

    @Test
    fun `ipv6 bracket hosts are rejected`() {
        // PY-069/070：java.net.URI 保留方括号（host="[::1]"）——Rust 对
        // authority 方括号形态一律拒绝，此处对齐
        assertNull(OriginPolicy.tryParseExternal("http://[::1]/"))
        assertNull(OriginPolicy.tryParseExternal("http://[::ffff:192.168.1.1]/"))
        assertNull(OriginPolicy.tryParseExternal("http://[::ffff:127.0.0.1]/"))
    }

    @Test
    fun `port zero is rejected`() {
        // PY-075：保留端口 0 不可用作目标（-1 = 未写端口保持放行）
        assertNull(OriginPolicy.tryParseExternal("https://example.org:0/"))
        assertNotNull(OriginPolicy.tryParseExternal("https://example.org/"))
    }

    @Test
    fun `ipv4 octets beyond 255 are rejected`() {
        // RS-228：四段全数字逐段 ≤255（WHATWG IPv4 解析器口径）
        assertNull(OriginPolicy.tryParseExternal("https://999.1.1.1/"))
        assertNull(OriginPolicy.tryParseExternal("https://256.0.0.1/"))
        assertNull(OriginPolicy.tryParseExternal("https://300.300.300.300/"))
        // 超长纯数字段（toInt 溢出）必然越界——fail-closed
        assertNull(OriginPolicy.tryParseExternal("https://99999999999999.1.1.1/"))
        // 合法边界保留
        assertNotNull(OriginPolicy.tryParseExternal("https://255.255.255.255/"))
        assertNotNull(OriginPolicy.tryParseExternal("https://93.184.216.34/"))
    }

    // ---------- AD-315（2026-10-02 审计）：跨端共享向量消费 ----------

    /** AD-315：加载共享向量（仓库根 contracts/vectors 相对定位——参照
     *  app 侧 SearchNormalizeVectorsTest 先例：工作目录向上游走找仓库根）。 */
    private fun loadSharedVectors(fileName: String): List<Pair<String, String>> {
        val path =
            generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
                .take(8)
                .map { it.resolve("contracts").resolve("vectors").resolve(fileName) }
                .firstOrNull { Files.isRegularFile(it) }
                ?: error("找不到共享向量 $fileName（相对仓库根定位失败）")
        val payload = JSONObject(String(Files.readAllBytes(path), Charsets.UTF_8))
        val vectors = payload.getJSONArray("vectors")
        return (0 until vectors.length()).map { vectors.getJSONObject(it) }
            .map { it.getString("url") to it.getString("expected") }
    }

    /**
     * AD-315：超长 URL 锚点物化——向量内的语义锚点 token（PY-078）由消费端
     * 物化为 https://example.org/ + 'a'×9000（> 8192 上限；与 Rust vectors.rs
     * 同口径——Kotlin 侧此前以 9000 字符字面样本覆盖，现随共享向量单源化）。
     */
    private fun materialize(url: String): String =
        if (url.endsWith("oversize-url-limit-test")) {
            "https://example.org/" + "a".repeat(9000)
        } else {
            url
        }

    @Test
    fun sharedUrlOriginVectorsMatchPolicyVerdict() {
        val valid = loadSharedVectors("url-origin-valid.json")
        val invalid = loadSharedVectors("url-origin-invalid.json")
        assertTrue("共享合法向量不得为空", valid.isNotEmpty())
        assertTrue("共享非法向量不得为空", invalid.isNotEmpty())
        valid.forEach { (url, _) ->
            assertNotNull(
                "共享向量判 allow 但 OriginPolicy 拒绝（url=「$url」）",
                OriginPolicy.tryParseExternal(materialize(url)),
            )
        }
        invalid.forEach { (url, _) ->
            assertNull(
                "共享向量判 deny 但 OriginPolicy 放行（url=「$url」）",
                OriginPolicy.tryParseExternal(materialize(url)),
            )
        }
    }

    @Test
    fun `trailing dot rejection mixes with alternate encoding vectors`() {
        // AD-274：尾点与备用编码混合形态同批锁定——任一混淆面命中即拒
        assertNull(OriginPolicy.tryParseExternal("https://localhost./x?token=1"))
        assertNull(OriginPolicy.tryParseExternal("https://LOCALHOST./"))
        assertNull(OriginPolicy.tryParseExternal("https://aegis.local.:8443/path"))
        // 对照组：无尾点的白名单/普通域保持放行（不因收窄误伤）
        assertNotNull(OriginPolicy.tryParseExternal("https://localhost/"))
        assertNotNull(OriginPolicy.tryParseExternal("https://aegis.local/home"))
        assertNotNull(OriginPolicy.tryParseExternal("https://example.com:8443/"))
    }
}

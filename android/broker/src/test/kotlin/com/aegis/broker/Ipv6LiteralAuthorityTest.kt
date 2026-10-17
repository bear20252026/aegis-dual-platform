package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * R9-B85（队列 Q68 裁决「判导航」）：地址栏 IPv6 字面量判据的单源用例。
 *
 * 三条线各自钉住一件事：合法字面量必须判成网址（含**裸冒号形态补方括号**，因为
 * `LocalTargetHosts.hostOf` 对缺括号的多冒号串返回空串）、括号里放点分 IPv4 必须
 * 判不成（`[8.8.8.8]`——`contracts/vectors/url-origin-invalid.json` 的双重解释面那条）、
 * 以及 `]` 之后只允许 `:端口`（不这么收，本端判网址而 Windows 判搜索词，正是本次要消灭的分叉）。
 */
class Ipv6LiteralAuthorityTest {
    @Test
    fun bracketedLiteralIsKeptVerbatim() {
        assertEquals("[::1]", Ipv6LiteralAuthority.canonicalize("[::1]"))
        assertEquals("[::1]:9000", Ipv6LiteralAuthority.canonicalize("[::1]:9000"))
        assertEquals("[fd12::3]", Ipv6LiteralAuthority.canonicalize("[fd12::3]"))
        assertEquals(
            "[2606:4700:4700::1111]:8443/api?x=1",
            Ipv6LiteralAuthority.canonicalize("[2606:4700:4700::1111]:8443/api?x=1"),
        )
        // 内嵌 IPv4 的合法写法（v4-mapped）是 IPv6，不是「括号里的点分串」
        assertEquals(
            "[::ffff:127.0.0.1]:8080",
            Ipv6LiteralAuthority.canonicalize("[::ffff:127.0.0.1]:8080"),
        )
    }

    @Test
    fun bareColonFormIsBracketedIntoTheCanonicalShape() {
        assertEquals("[::1]", Ipv6LiteralAuthority.canonicalize("::1"))
        assertEquals("[::1]/api", Ipv6LiteralAuthority.canonicalize("::1/api"))
        // 裸写法里「地址段」与「端口」按文本无法区分，正典形态即整段进括号——
        // Windows 的 BracketIpv6 同判，两端在这条上必须给出同一个地址而不是各猜一次
        assertEquals("[::1:8080]", Ipv6LiteralAuthority.canonicalize("::1:8080"))
    }

    @Test
    fun bracketedDottedIpv4IsNotAnIpv6Literal() {
        assertNull(Ipv6LiteralAuthority.canonicalize("[8.8.8.8]"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[8.8.8.8]:8080"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[127.0.0.1]"))
    }

    @Test
    fun formsThatDoNotStartLikeAnIpv6AuthorityAreRejected() {
        // 字母起始读起来像 scheme；数字起始的裸 IPv6 两端都维持「不是网址」
        assertNull(Ipv6LiteralAuthority.canonicalize("fe80::1"))
        assertNull(Ipv6LiteralAuthority.canonicalize("2606:4700:4700::1111"))
        assertNull(Ipv6LiteralAuthority.canonicalize("nas.local"))
        assertNull(Ipv6LiteralAuthority.canonicalize("weather forecast"))
        assertNull(Ipv6LiteralAuthority.canonicalize(""))
    }

    @Test
    fun malformedBracketShapesAreRejected() {
        assertNull(Ipv6LiteralAuthority.canonicalize("[]"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[::1"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[::1]x"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[::1]:abc"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[::1]:123456"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[fe80::1%eth0]"))
        assertNull(Ipv6LiteralAuthority.canonicalize("[::1::2]"))
    }

    @Test
    fun surroundingWhitespaceAndUpperCaseHexAreNormalizedForParsingOnly() {
        assertEquals("[::1]", Ipv6LiteralAuthority.canonicalize("   [::1]   "))
        // 正面控制：小写化只喂给解析器，输出保留调用方给的字符（大小写差异属
        // 两端既有契约，不能让判据在这里悄悄改写文本）
        assertEquals("[FF12::3]", Ipv6LiteralAuthority.canonicalize("[FF12::3]"))
    }
}

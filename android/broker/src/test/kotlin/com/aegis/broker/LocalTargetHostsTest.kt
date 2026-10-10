package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ②（第八轮 2026-10-07）：本机/内网目标判定的常驻回归锁。
 *
 * 三点都在防具体事故：
 * • **零 DNS**——本用例是纯 JVM 的（不 import Android 类型），任何同步解析都会让它在
 *   无网 CI 上直接变慢或变红；CS-382 的冻结面就是这样被钉住的。
 * • **段集与孪生同侧**——放行面按第七轮 B8 裁决（本机与内网必须能打开）写死；
 *   云元数据/链路本地/TEST-NET/组播/广播/非常规 IPv4 编码必须**不**豁免。
 * • 单标签名与 IPv6 ULA 的边界都是显式决定，不是顺手。
 */
class LocalTargetHostsTest {
    @Test
    fun hostExtractionCoversEveryUrlShape() {
        val cases =
            listOf(
                "http://192.168.1.1:8080/admin" to "192.168.1.1",
                "HTTP://LOCALHOST:8000/" to "localhost",
                "http://user:pass@nas.local/x" to "nas.local",
                "http://[::1]:9/" to "::1",
                "http://[fd12::3]/" to "fd12::3",
                "http://[fd12::3]:8443/x" to "fd12::3",
                "https://example.com/a?b=#c" to "example.com",
                "192.168.1.1:8080" to "192.168.1.1",
                "http:example.com" to "http", // 无 "//" 的畸形形态：剥不到 host，交回不豁免
                "http://fd12::3/" to "", // 裸 IPv6（缺方括号）：空串＝判不出 host，交回不豁免
                "http://fe80::1:8080/" to "",
            )
        for ((url, expected) in cases) {
            assertEquals("hostOf($url)", expected, LocalTargetHosts.hostOf(url))
        }
    }

    /**
     * R9-AD-4（第九轮 2026-10-10）：三处判定对方括号 IPv6 字面量的结果**故意不同**，
     * 这条用例把差异钉住，防止任何一侧被当成缺陷顺手改。
     *
     * • 导航入口 [OriginPolicy] 拒（AD-299：与 Rust origin/host_grammar 及 contracts 的
     *   url-origin-invalid 向量同口径——java.net.URI 保留方括号而 Chromium 剥，
     *   双重解释面宁可不放行）；
     * • host 一旦剥了括号（[LocalTargetHosts.hostOf] 的职责），::1/ULA 就落在第七轮 B8
     *   裁决的放行段里——HTTPS 升级豁免层与下载层看到的正是这个形态。
     *
     * 代价如实记：地址栏输 `http://[::1]:9000/` 在 Android 打不开，而 Windows 能。
     * 要打通它得解冻核心 host grammar 并增补 url-origin-* 向量（三端解析器语义变更），
     * 已报待用户定稿；**不得**用「收紧段集」来消除这条差异——裁决是本机与内网必须能打开。
     */
    @Test
    fun bracketedIpv6IsRejectedForNavigation_ButExemptOnceHostIsStripped() {
        assertNull(OriginPolicy.tryParseExternal("http://[::1]:9000/"))
        assertTrue(LocalTargetHosts.isLocalTarget(LocalTargetHosts.hostOf("http://[::1]:9000/")))
        assertFalse(ReservedAddressBoundary.denies("http://[::1]:9000/"))
    }

    @Test
    fun localAndLanTargetsAreExempt() {
        val exempt =
            listOf(
                "localhost",
                "my.localhost",
                "foo.localhost",
                "my-nas.local",
                "printer.internal",
                "127.0.0.1",
                "127.5.6.7",
                "10.0.0.5",
                "172.16.0.1",
                "172.31.255.254",
                "192.168.1.1",
                "100.64.1.2",
                "100.127.255.255",
                "::1",
                "fd12:3456::7",
                "fc00::1",
            )
        for (host in exempt) {
            assertTrue("$host 应豁免（本机/内网必须能打开）", LocalTargetHosts.isLocalTarget(host))
        }
    }

    @Test
    fun nonLocalTargetsStayOnHttps() {
        val denied =
            listOf(
                "169.254.169.254", // 链路本地含云元数据
                "169.254.1.1",
                "0.0.0.0",
                "192.0.2.1", // TEST-NET-1
                "198.51.100.7", // TEST-NET-2
                "203.0.113.9", // TEST-NET-3
                "198.18.0.1", // 基准段
                "224.0.0.1", // 组播
                "255.255.255.255", // 广播
                "8.8.8.8",
                "example.com",
                "www.baidu.com",
                "nas", // 单标签名：判定需 DNS，不在零 DNS 契约内
                "fe80::1", // IPv6 链路本地
                "ff02::1",
                "fe80::1%25eth0", // zone-id：要接口知识，不在零 DNS 契约内
                "::1%eth0", // 连回环带 zone-id 也不豁免（CS-201 同型）
                "0177.0.0.1", // 前导零八进制
                "2852168190", // 十进制整数编码
                "0x7f000001", // 十六进制编码
                "127.1", // 简写段数
                "",
            )
        for (host in denied) {
            assertFalse("$host 不该豁免", LocalTargetHosts.isLocalTarget(host))
        }
    }

    @Test
    fun exemptionFollowsTheUrlNotTheCaller() {
        assertTrue(LocalTargetHosts.isExemptFromHttpsUpgrade("http://192.168.1.1:8080/admin"))
        assertTrue(LocalTargetHosts.isExemptFromHttpsUpgrade("http://my-nas.local/"))
        assertFalse(LocalTargetHosts.isExemptFromHttpsUpgrade("http://example.com/"))
        assertFalse(LocalTargetHosts.isExemptFromHttpsUpgrade("http://169.254.169.254/latest/meta-data/"))
    }
}

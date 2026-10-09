package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 保留地址边界（R8-AD-03）的纯 JVM 用例。
 *
 * 为什么值得单独钉：下载交系统 `DownloadProvider` 发请求，那是另一个进程 ⇒
 * 本 app 的 NSC（禁明文）管不到它，所以「明文 + 链路本地（云元数据）」这类在导航层
 * 被拒、在子资源层被 NSC 挡的形态，在下载层此前完整绕过。判据能不能信，只看两件事：
 * **保留段是否真的被拦**、**B8 裁决要求能打开的本机/内网是否真的没被顺手拦**。
 * 两组用例必须同时存在——只留拒绝组，这条谓词可以在"全拒"下悄悄全绿。
 */
class ReservedAddressBoundaryTest {
    @Test
    fun reservedSegmentsAreDenied() {
        val denied =
            listOf(
                // 链路本地（云厂商实例元数据在其内）
                "http://169.254.169.254/latest/user-data",
                "http://169.254.1.1/",
                // 未指定 / 组播 / 广播 / 保留
                "http://0.0.0.0/x",
                "http://224.0.0.1/",
                "http://239.255.255.250/",
                "http://255.255.255.255/",
                "http://240.0.0.1/",
                // 文档与基准测试段
                "http://192.0.2.3/",
                "http://198.51.100.4/",
                "http://203.0.113.5/",
                "http://198.18.0.1/",
                "http://198.19.254.3/",
                // IPv6：:: 未指定、fe80::/10 链路本地、ff00::/8 组播、内嵌 IPv4
                "http://[::]/",
                "http://[fe80::1]/",
                "http://[ff02::1:2]/",
                "http://[::ffff:169.254.169.254]/",
                "http://[::ffff:garbage]/",
                // 与 OS 解释分歧的数字形态（CS-348/AD-213 同族）
                "http://2852168190/",
                "http://0xa9fea9fe/",
                "http://0177.0.0.1/",
                "http://169.1/",
                "http://169.254.1/",
            )
        for (url in denied) {
            assertTrue("保留地址必须拒绝：$url", ReservedAddressBoundary.denies(url))
        }
    }

    @Test
    fun loopbackPrivateAndCgnatStayOpenableByRuling() {
        // 第七轮 B8「本机与内网必须能打开」——这一组是这条裁决在下载层的下界，
        // 谁把它们收紧了，本用例就是那条反向证。
        val allowed =
            listOf(
                "http://127.0.0.1:8000/",
                "http://[::1]:9000/",
                "http://10.0.0.5/",
                "http://172.16.0.1/",
                "http://172.31.255.255/",
                "http://192.168.1.1:8080/file.zip",
                "http://100.64.1.2/",
                "http://[fd12::3]/",
                "http://localhost:8000/",
                "http://api.localhost/x",
                "http://my-nas.local/share.bin",
                "http://printer.internal/firmware",
                "https://example.com/a.apk",
            )
        for (url in allowed) {
            assertFalse("本机/内网/公网目标不得被这条边界拦：$url", ReservedAddressBoundary.denies(url))
        }
    }

    @Test
    fun undecidableHostsDenyFailClosed() {
        // 切不出 host、zone-id（要接口知识）⇒ 不可判定即不放行。
        assertTrue(ReservedAddressBoundary.denies("http:///x"))
        assertTrue(ReservedAddressBoundary.denies("http://[fe80::1%eth0]/"))
        assertTrue(ReservedAddressBoundary.deniesHost(""))
        assertTrue(ReservedAddressBoundary.deniesHost("169.254.169.254.")) // 尾点不改判定
    }

    @Test
    fun denyCodeMatchesTheWindowsTwin() {
        // 拒绝码跨端单源：审计按码聚合，字符串分叉就等于两套账。
        assertEquals("reserved_address", ReservedAddressBoundary.DENY_CODE)
    }

    @Test
    fun adjacentAddressesOnBothSidesOfEverySegment() {
        // 逐段左右邻：只测被点名的地址，会放过「段边界写错一位」这种缺陷。
        assertTrue(ReservedAddressBoundary.deniesHost("169.254.0.1"))
        assertFalse(ReservedAddressBoundary.deniesHost("169.253.255.254")) // 链路本地段的下邻
        assertTrue(ReservedAddressBoundary.deniesHost("224.0.0.0"))
        assertFalse(ReservedAddressBoundary.deniesHost("223.255.255.254")) // 组播段的下邻
        assertTrue(ReservedAddressBoundary.deniesHost("198.18.0.0"))
        assertFalse(ReservedAddressBoundary.deniesHost("198.17.255.255")) // 基准段的下邻
        assertFalse(ReservedAddressBoundary.deniesHost("127.0.0.1")) // 回环按 B8 放行
        // 已知残余照抄 Windows 侧的账：阿里云元数据落在放行的 CGNAT 段内，不假装已封
        assertFalse(
            "已知残余：100.100.100.200 按第七轮 B8 裁决放行（台账记过）",
            ReservedAddressBoundary.deniesHost("100.100.100.200"),
        )
        // 第二条已知残余：GCP 元数据端点是**主机名**——本谓词零 DNS，无从判它指向哪里，
        // 权威在 DNS/OS 侧。写在这里是「残余」而不是「已封」的口径，与 Windows 同账。
        assertFalse(
            "已知残余：metadata.google.internal 是主机名 ⇒ 本谓词不判，权威交 DNS",
            ReservedAddressBoundary.deniesHost("metadata.google.internal"),
        )
    }
}

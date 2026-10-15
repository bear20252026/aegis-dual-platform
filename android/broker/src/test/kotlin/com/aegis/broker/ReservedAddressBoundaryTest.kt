package com.aegis.broker

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path

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
    /**
     * ① 谓词表：逐条消费跨端契约向量 reserved-address-boundary.json（R9-B70）。
     *
     * 改这张表之前它与 C# 的 `BoundaryMatrix` 各抄一份，实测**只有 12 条是同一个 URL**——
     * 其余各测各的，「两端都判了这条边界」因此是覆盖假象；而且同一条 URL 已经出现相反期望
     * （`http://0177.0.0.1/` 在 C# 放行、在本端拒）。现在两端跑同一份表：谁改了判定面而
     * 没同批改表，那一端就判红。
     *
     * 分层事实（R9-AD-4）留在表注里：本层的 host 由 hostOf 剥过方括号 ⇒ `[::1]` 在这里可下载，
     * 而同一条 URL 在导航层被 OriginPolicy 拒（三端与 url-origin-* 向量同口径）。
     */
    @Test
    fun sharedBoundaryVectorsMatchPredicateVerdict() {
        for ((url, expected) in loadSharedBoundaryVectors()) {
            val denied = ReservedAddressBoundary.denies(url)
            assertEquals(
                "契约向量说 $expected 但 denies=$denied（url=$url）",
                expected == "deny",
                denied,
            )
        }
    }

    private fun loadSharedBoundaryVectors(): List<Pair<String, String>> {
        val path =
            generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
                .take(8)
                .map { it.resolve("contracts").resolve("vectors").resolve(BOUNDARY_VECTOR) }
                .firstOrNull { Files.isRegularFile(it) }
                ?: error("找不到共享向量 $BOUNDARY_VECTOR（相对仓库根定位失败）")
        val vectors = JSONObject(String(Files.readAllBytes(path), Charsets.UTF_8)).getJSONArray("vectors")
        val loaded =
            (0 until vectors.length())
                .map { vectors.getJSONObject(it) }
                .map { it.getString("url") to it.getString("expected") }
        check(loaded.size >= BOUNDARY_FLOOR) {
            "契约向量 ${loaded.size} 条，低于下界 $BOUNDARY_FLOOR——清空条目须显式核减（与 verify_vectors 同口径）"
        }
        val unknown = loaded.map { it.second }.filter { it != "deny" && it != "allow" }.distinct()
        check(unknown.isEmpty()) { "契约向量 expected 词表外：$unknown" }
        return loaded
    }

    private companion object {
        const val BOUNDARY_VECTOR = "reserved-address-boundary.json"
        const val BOUNDARY_FLOOR = 40
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

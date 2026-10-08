package com.aegis.webviewadapter

import com.aegis.broker.AndroidBroker
import org.junit.Assert.assertEquals
import org.junit.Test
import org.mockito.Mockito.mock

/**
 * ②（第八轮 2026-10-07，用户定稿）：HTTPS-only 升级对本机/内网目标的豁免。
 *
 * 此前这里是**无条件**升级：远程页 http 升 https 是对的，但 dev server、NAS、打印机
 * 多数只跑 http，升级即 ERR_CERT_* / 连接重置——第七轮 B8「本机与内网必须能打开」
 * 因此在这一层从未落地（Windows 侧由 CS-382/388 落了，Android 侧没有孪生）。
 *
 * 判据单源在 broker 的 `LocalTargetHosts`（纯字符串、零 DNS），本用例因此能在
 * 无设备、无网络的 JVM 门禁里跑——CS-382 那一类「UI 线程同步解析」的回归，
 * 只有能被机器拦住才算被拦住。`upgradeToHttpsIfNeeded` 为此从 private 提为
 * internal：这条判定此前只能靠真机验证，等于没有回归保护。
 *
 * **与 Windows 的豁免面不等宽，且两端都到不了云元数据**（残余差异登记 R8-CS-SEC-17；
 * Windows 的**输入层**已在 R8-CS-SEC-15 与本端合一，两处都问同一个判据）：
 * Windows 的 `IsExemptFromHttpsUpgrade` 判据是 `!UrlSafety.IsPublicHost(host)`，
 * 链路本地（含 `169.254.169.254`）属「非公网」⇒ 在 Windows **不升级**，改由导航层
 * `ReservedAddressBoundary.Denies` 拒绝；Android 没有那一层托管判据，就在升级层把它
 * 留在 https。同一 URL 两端的处置动作不同（一个是 denied 码、一个是连接失败），
 * 但结果一致：元数据端点打不开。前导零八进制（`0177.0.0.1`）方向相反——Windows
 * 归一为 127.0.0.1 后豁免、Android 不豁免，Android 侧宁可多升一次 https。
 */
class AegisWebViewClientHttpsUpgradeTest {
    private fun client(): AegisWebViewClient =
        AegisWebViewClient(
            broker = mock(AndroidBroker::class.java),
            sessionId = "s1",
            tabId = "t1",
            onRendererGone = {},
        )

    @Test
    fun remoteHttpStillUpgrades() {
        val c = client()
        assertEquals("https://example.com/x", c.upgradeToHttpsIfNeeded("http://example.com/x"))
        val metadata = "http://169.254.169.254/latest/meta-data/"
        assertEquals("https://169.254.169.254/latest/meta-data/", c.upgradeToHttpsIfNeeded(metadata))
        assertEquals("https://0177.0.0.1/", c.upgradeToHttpsIfNeeded("http://0177.0.0.1/"))
    }

    @Test
    fun localAndLanTargetsStayOnHttp() {
        val c = client()
        val exempt =
            listOf(
                "http://localhost:8000/",
                "http://127.0.0.1:9/",
                "http://my-nas.local/",
                "http://printer.internal/",
                "http://192.168.1.1:8080/admin",
                "http://10.0.0.5/",
                "http://[::1]/",
                "http://[fd12::3]/",
                "http://[fc00::1]:8080/x",
            )
        for (url in exempt) {
            assertEquals("本机/内网目标不得被升级拦死：$url", url, c.upgradeToHttpsIfNeeded(url))
        }
    }

    @Test
    fun malformedIpv6AuthorityFailsClosed() {
        // 裸 IPv6 authority（缺方括号）不是合法 URL：hostOf 按 host:port 取到的是
        // 首段，判不出内网 ⇒ 照常升级。方向必须是「多升一次 https」而不是放行明文。
        val c = client()
        assertEquals("https://fe80::1/", c.upgradeToHttpsIfNeeded("http://fe80::1/"))
        assertEquals("https://fd12::3/", c.upgradeToHttpsIfNeeded("http://fd12::3/"))
    }

    @Test
    fun nonHttpSchemesAreUntouchedHere() {
        // 本函数只管 http→https；非 http 的 scheme 由 OriginPolicy/broker 那一层拒绝，
        // 在这里「顺手处理」会造出第二个判定源（第七轮 R7-CS1 系列的老形态）。
        val c = client()
        assertEquals("https://example.com/", c.upgradeToHttpsIfNeeded("https://example.com/"))
        assertEquals("about:blank", c.upgradeToHttpsIfNeeded("about:blank"))
        assertEquals("file:///etc/passwd", c.upgradeToHttpsIfNeeded("file:///etc/passwd"))
    }
}

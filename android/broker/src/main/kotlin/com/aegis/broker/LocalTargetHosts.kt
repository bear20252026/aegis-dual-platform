package com.aegis.broker

/**
 * 本机与内网目标判定（②，第八轮 2026-10-07；裁决源是第七轮 B8「本机与内网必须能打开」）。
 *
 * 三条契约写在这里，因为破坏它们的代价本仓都付过：
 * 1. **纯字符串、零 DNS**。它同时被输入分类（UI 线程）与 WebView 的升级判定调用，
 *    一次同步解析就是 CS-382 的冻结面——「恶意页连开数个 hosts 域链接即冻结 UI」。
 * 2. **JVM 可测**（不 import 任何 Android 类型）：webview-adapter 的判定面此前只能靠
 *    真机，等于没有回归保护。
 * 3. **段集与孪生同侧**：Rust `security_policy::is_high_risk_host` 与 Windows
 *    `ReservedAddressBoundary` 放行回环 / RFC1918 / CGNAT(100.64/10) / ULA(fc00::/7)，
 *    不豁免链路本地（含云元数据 `169.254.169.254`）、`0/8`、TEST-NET-1/2/3、
 *    `198.18/15`、组播与广播；`localhost`/`.localhost`/`.local`/`.internal` 这类
 *    **名字后缀**在 Windows 由 `UrlSafety.IsPublicHost` 判（本仓无第三个名字判据）。
 *
 * Windows 的**输入层补 scheme**（`Chrome/UrlNormalizer.SchemeForLocal`）自 R8-CS-SEC-15
 * （2026-10-08）起与本端同构：两端都不再各自写一套「猜 scheme」规则，而是各问一次自己的
 * 「这是本机/内网目标吗」（本端 = 下面的段集；Windows = `UrlSafety.IsPublicHost` 取反，
 * 与它的 HTTPS-only 升级豁免层同一个判据），并由**共享向量文件**
 * `app/src/test/resources/search-normalize-vectors.json` 两端各自逐条消费钉住。
 *
 * 残余不等宽（转登 R8-CS-SEC-17）：Windows 的「非公网」比本端段集**宽**——链路本地
 * （`169.254/16`）、TEST-NET、`198.18/15`、组播/广播，以及八进制/整数/简写编码归一后
 * 落进保留段的形态，在 Windows 补 http、在本端补 https。终态两端一致（这些地址都在
 * 导航边界被拒，云元数据谁都打不开），差的只是处置动作：Windows 给 denied 码、
 * Android 是连接失败或 https 报错。**不要**把这条差异当 SSRF 缺陷去「收紧」Windows——
 * 裁决是「本机与内网必须能打开」，方向只有放宽本机可达，不是反过来。
 *
 * 两处刻意不豁免，都写清理由，免得下轮当缺陷「顺手修」：
 * • **单标签主机名**（`nas`、`printer`）：判它是不是内网要问 DNS，本函数的契约是零 DNS
 *   ——Windows 的公网判定同口径（`IsPublicHost("nas")` 为真 ⇒ 升级层不豁免）。请用 IP
 *   或 `.local`。
 * • **前导零八进制 / 整数 / 十六进制 / 简写等非常规 IPv4 编码**（`0251.0376…`、
 *   `2852168190`、`127.1`）：Chromium 按 inet_aton 解释、.NET 与本机解释不一致，
 *   两侧口径不同就是绕过面（CS-348/CS-418 记过），因此一律不豁免。方向是**宁可多升
 *   一次 https**（打不开比走明文安全）；Windows 侧则把这些形态归一后判——`0177.0.0.1`
 *   归一成 127.0.0.1 ⇒ 输入层补 http、升级层豁免，但 `OriginPolicy` 在导航层按 raw
 *   authority 同判拒绝（AD-213 孪生）。Android 在 normalize 链内就返回 null，Windows 到
 *   导航层才拒：**层序不同、终态相同**，此差异归 R8-CS-SEC-17（共享向量的
 *   `windows_url` 覆盖 + Windows 消费端两条断言把「两条都成立」钉住）。
 *
 * • **方括号 IPv6 字面量在导航层就到不了本函数**（R9-AD-4，第九轮 2026-10-10）：
 *   `OriginPolicy` 对 authority 里的 `[` 一律拒（AD-299，与 Rust `origin/host_grammar`
 *   及 contracts 的 url-origin-invalid 向量同口径——java.net.URI 保留括号而 Chromium 剥，
 *   双重解释面宁可不放行）。所以本函数对 `::1`/ULA 的豁免**实际覆盖的是已剥括号的 host
 *   形态**：HTTPS 升级豁免层（`hostOf` 之后）与下载层（`ReservedAddressBoundary`）。
 *   用户可见后果：地址栏输 `http://[::1]:9000/` 在 Android 打不开，Windows 却能——
 *   这条差异要消掉得解冻核心 host grammar 并增补向量（三端解析器语义变更），已报待定稿。
 *   由 `LocalTargetHostsTest.bracketedIpv6IsRejectedForNavigation_ButExemptOnceHostIsStripped`
 *   钉住三侧结果，**不得**反向收紧段集来「对齐」。
 */
object LocalTargetHosts {
    private const val SCHEME_SEPARATOR = "://"
    private val LOCAL_SUFFIXES = listOf(".localhost", ".local", ".internal")

    /** ULA 首字节前缀（fc00::/7 的 0xfc/0xfd）。 */
    private val ULA_PREFIXES = setOf("fc", "fd")

    /** 点分十进制的段数与单段上限。 */
    private const val IPV4_OCTETS = 4
    private const val OCTET_MAX_DIGITS = 3
    private const val OCTET_MAX = 255

    /**
     * 放行段表（第七轮 B8 裁决）。命名而不是就地写数字：这张表就是本函数的语义，
     * 而 detekt 的 MagicNumber 也只认命名后的形态。
     */
    private const val LOOPBACK_FIRST = 127
    private const val PRIVATE_A_FULL = 10
    private const val PRIVATE_B_FIRST = 172
    private val PRIVATE_B_SECOND = 16..31
    private const val PRIVATE_C_FIRST = 192
    private const val PRIVATE_C_SECOND = 168
    private const val CGNAT_FIRST = 100
    private val CGNAT_SECOND = 64..127

    /** 取 URL/authority 的 host：小写、剥 scheme、userinfo、端口与 IPv6 方括号。 */
    fun hostOf(url: String): String {
        var rest = url.trim().lowercase()
        val schemeEnd = rest.indexOf(SCHEME_SEPARATOR)
        if (schemeEnd >= 0) {
            rest = rest.substring(schemeEnd + SCHEME_SEPARATOR.length)
        }
        val boundary = rest.indexOfAny(charArrayOf('/', '?', '#'))
        if (boundary >= 0) {
            rest = rest.substring(0, boundary)
        }
        val at = rest.lastIndexOf('@')
        if (at >= 0) {
            rest = rest.substring(at + 1)
        }
        val close = rest.indexOf(']')
        // 带括号的 IPv6 字面量：方括号内不含端口，剥括号即为 host；
        // 其余形态按 host:port 剥末段冒号（无冒号时原样返回）。
        return if (rest.startsWith("[") && close > 0) {
            rest.substring(1, close)
        } else if (rest.count { it == ':' } > 1) {
            // 裸 IPv6 authority（缺方括号）不是 host:port 形态：按最后一个冒号切会切出
            // 「fd12:」这类假 host，反而把 ULA 判进来。返回空串 ⇒ 交回不豁免（fail-closed）。
            ""
        } else {
            rest.substringBeforeLast(':', rest)
        }
    }

    /**
     * host 是否属「本机或内网」目标（② 的放行面）。
     *
     * 三条不豁免的形态各有理由：zone-id（`fe80::1%eth0`）要接口知识、不在零 DNS 契约内；
     * 方括号残留属形态不合法；段数不是 4 的点分串（含 `nas` 这类单标签名）要问 DNS。
     */
    fun isLocalTarget(host: String): Boolean {
        val h = host.trim().lowercase().trimEnd('.')
        return when {
            h.isEmpty() -> false
            h == "localhost" || LOCAL_SUFFIXES.any { h.endsWith(it) } -> true
            h.contains('%') || h.startsWith("[") || h.endsWith("]") -> false
            h.contains(':') -> isExemptIpv6(h)
            else -> isExemptIpv4(h)
        }
    }

    /** http URL 是否免于升 https（调用方负责确认 scheme 确为 http）。 */
    fun isExemptFromHttpsUpgrade(url: String): Boolean = isLocalTarget(hostOf(url))

    /**
     * 点分十进制的放行面（第七轮 B8 裁决）：回环 127/8、RFC1918、CGNAT 100.64/10。
     * 其余一律不豁免——含 169.254/16 链路本地（云元数据在其内）、0/8、TEST-NET-1/2/3、
     * 198.18/15 基准段、224/4 组播、240/4 保留，以及公网。
     *
     * 段判定就地写在 `when (values[0])` 上，不拆成 `(a, b)` 两参私有函数：本仓
     * ktlint_official 的 function-signature 对「两参数 + 多行体」要求逐参数换行
     * （第八轮三轮红灯里第三轮就是这个），而那样只是把格式争论搬进签名行。
     */
    private fun isExemptIpv4(host: String): Boolean {
        val values = host.split('.').map { text -> octetValueOrMinusOne(text) }
        if (values.size != IPV4_OCTETS || values.any { it < 0 }) {
            return false
        }
        return when (values[0]) {
            LOOPBACK_FIRST, PRIVATE_A_FULL -> true
            PRIVATE_B_FIRST -> values[1] in PRIVATE_B_SECOND
            PRIVATE_C_FIRST -> values[1] == PRIVATE_C_SECOND
            CGNAT_FIRST -> values[1] in CGNAT_SECOND
            else -> false
        }
    }

    /** 单个点分段的合法形态：1-3 位纯数字、无前导零（`0` 本身除外）。 */
    private fun isDecimalOctet(text: String): Boolean =
        text.length in 1..OCTET_MAX_DIGITS && text.all { it.isDigit() } && (text == "0" || !text.startsWith("0"))

    /** 合法段 → 0..255，否则 -1。前导零八进制（`0177`）走 -1：见对象注释。 */
    private fun octetValueOrMinusOne(text: String): Int {
        if (!isDecimalOctet(text)) {
            return -1
        }
        val value = text.toInt()
        return if (value in 0..OCTET_MAX) value else -1
    }

    private fun isExemptIpv6(host: String): Boolean = host == "::1" || isUla(host.substringBefore(':'))

    /**
     * ULA fc00::/7——首字节 0xfc/0xfd，裁决放行的内网单播；
     * fe80 链路本地、ff02 组播都不在面内。
     */
    private fun isUla(firstGroup: String): Boolean = firstGroup.take(2) in ULA_PREFIXES
}

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
 * 与 Windows 的**输入层补 scheme**（`Chrome/UrlNormalizer.SchemeForLocal`）并不同口径：
 * 那边对**任意** IP 字面量（含 `169.254.169.254`、公网 IP）补 http，且只认 localhost
 * 家族（`.local`/`.internal` 补 https）。本端按段集判定，因此同一份裁决在两端的
 * 「猜 scheme」这一步结论可以相反——差异已登记台账（R8-CS-SEC-15），归下一批收敛，
 * 本批不把单端改动伪装成三端一致。
 *
 * 两处刻意不豁免，都写清理由，免得下轮当缺陷「顺手修」：
 * • **单标签主机名**（`nas`、`printer`）：判它是不是内网要问 DNS，本函数的契约是零 DNS
 *   ——Windows 的公网判定同口径（`IsPublicHost("nas")` 为真 ⇒ 升级层不豁免）。请用 IP
 *   或 `.local`。
 * • **前导零八进制 / 整数 / 十六进制 / 简写等非常规 IPv4 编码**（`0251.0376…`、
 *   `2852168190`、`127.1`）：Chromium 按 inet_aton 解释、.NET 与本机解释不一致，
 *   两侧口径不同就是绕过面（CS-348/CS-418 记过），因此一律不豁免。方向是**宁可多升
 *   一次 https**（打不开比走明文安全）；Windows 侧则把这些形态归一后交给
 *   `ReservedAddressBoundary` 判（`0177.0.0.1` 归一成 127.0.0.1 ⇒ 被豁免），
 *   两端在此不完全一致，同上归 R8-CS-SEC-15 收敛。
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

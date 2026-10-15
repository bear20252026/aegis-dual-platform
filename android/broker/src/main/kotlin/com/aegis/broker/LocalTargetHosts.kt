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
 * • **方括号 IPv6 字面量自 R9-B66（队列 Q4 第二半）起在导航层被收下**，两端差异随之消掉：
 *   以前 `OriginPolicy` 对 authority 里的 `[` 一律拒（R9-AD-4 记录的那条「地址栏输
 *   `http://[::1]:9000/` 在 Android 打不开、Windows 能」），现在三端解析器同口径——
 *   语法收下、由本函数与核心 `security_policy/ipv6.rs` 按字节分类。本函数的入参契约
 *   不变：调用面一律先过 [hostOf]（已剥括号），导航边界要的是「这串括号里的地址合法吗」，
 *   它直接调 [AddressText.ipv6ToBytes] 而不是本函数。判据只有一份：**先认回环 `::1`，再折叠内嵌
 *   IPv4，最后看段集**——顺序不可换，v4-compatible 折叠会把 `::1` 读成 `0.0.0.1`
 *   而撞上 0/8。由 `LocalTargetHostsTest.ipv6BracketedLiteralIsParsedAndClassifiedByBytes`
 *   钉住，**不得**反向收紧段集来「对齐」（裁决是「本机与内网必须能打开」）。
 */
object LocalTargetHosts {
    private const val SCHEME_SEPARATOR = "://"
    private val LOCAL_SUFFIXES = listOf(".localhost", ".local", ".internal")

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
        val values = host.split('.').map { text -> AddressText.octetValueOrMinusOne(text) }
        if (values.size != AddressText.IPV4_OCTETS || values.any { it < 0 }) {
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

    /**
     * IPv6 的放行面（R9-B66 / 队列 Q4 第二半）。**先转字节再判**——
     * 与核心 `security_policy/ipv6.rs`、Windows `UrlSafety.IsPublicIp` 同一个理由：
     * 同一地址有 N 种合法拼法（`::ffff:127.0.0.1`、`::ffff:7f00:1`、
     * `0:0:0:0:0:ffff:7f00:1`），按文本前缀判必然出现「一种拼法豁免、另一种不豁免」，
     * 而那在三端共用向量的契约下就是红灯；折叠成 16 字节后只有一份语义。
     * 解析不了（含 zone-id、方括号残留、段数超限）→ false，即不豁免 = 维持升 https，
     * 方向是安全侧。文本解析本身在 [AddressText]（本文件只留分类）。
     */
    private fun isExemptIpv6(body: String): Boolean =
        when (val bytes = AddressText.ipv6ToBytes(body)) {
            null -> false
            else -> isLoopbackV6(bytes) || (embeddedIpv4(bytes)?.let { isExemptIpv4(it) } ?: isUla(bytes))
        }

    /** `::1`——必须用 `contentEquals`：数组的 `==` 比的是引用，`::1` 永远不相等。 */
    private fun isLoopbackV6(bytes: ByteArray): Boolean = bytes.contentEquals(LOOPBACK_V6_BYTES)

    /**
     * 内嵌 IPv4（v4-mapped `::ffff:x` 与已废弃的 v4-compatible `::x`）折成点分文本，
     * 两种形态都不是时返回 null。
     *
     * 折叠必须排在回环判定**之后**（`isExemptIpv6` 的条目顺序就是这条口径）：`::1`
     * 折出来是 `0.0.0.1`，而 0/8 不在放行段表里——B8 裁决要求放行的本机回环会被
     * 自己人拦掉。核心 `security_policy/ipv6.rs` 与 Windows `UrlSafety.IsPublicIp`
     * 是同一条顺序，改这里必须同时改那两处。
     */
    private fun embeddedIpv4(bytes: ByteArray): String? {
        val headIsZero = bytes.take(IPV6_IPV4_PREFIX).all { it == 0.toByte() }
        val tailStart = bytes.size - AddressText.IPV4_OCTETS
        val isMapped = bytes[IPV6_MAPPED_A] == MAPPED_MARKER && bytes[IPV6_MAPPED_B] == MAPPED_MARKER
        val isCompatible = (IPV6_IPV4_PREFIX until tailStart).all { bytes[it] == 0.toByte() }
        return if (headIsZero && (isMapped || isCompatible)) {
            bytes.takeLast(AddressText.IPV4_OCTETS).joinToString(".") { (it.toInt() and OCTET_MASK).toString() }
        } else {
            null
        }
    }

    private fun isUla(bytes: ByteArray): Boolean {
        val firstOctet = bytes[FIRST_OCTET].toInt() and ULA_HIGH_BITS_MASK
        return firstOctet == ULA_HIGH_BITS
    }

    /**
     * ULA fc00::/7 的首字节掩码判据；fe80 链路本地与 ff00::/8 组播都不在放行面内。
     */
    private const val ULA_HIGH_BITS_MASK = 0xfe
    private const val ULA_HIGH_BITS = 0xfc
    private const val IPV6_IPV4_PREFIX = 10
    private const val IPV6_MAPPED_A = 10
    private const val IPV6_MAPPED_B = 11
    private const val MAPPED_MARKER = 0xff.toByte()
    private const val OCTET_MASK = 0xff
    private const val FIRST_OCTET = 0

    private val LOOPBACK_V6_BYTES =
        ByteArray(AddressText.IPV6_BYTES).also { it[AddressText.IPV6_BYTES - 1] = 1.toByte() }
}

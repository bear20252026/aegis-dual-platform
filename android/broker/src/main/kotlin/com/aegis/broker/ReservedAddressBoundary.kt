package com.aegis.broker

/**
 * 保留地址边界（Android 侧孪生；段表与 C# `Broker.ReservedAddressBoundary`、
 * Rust `security_policy::is_high_risk_host` 同侧）。判定为真 = 拒绝。
 *
 * 只拦**根本不是任何设备**的地址形态：`0.0.0.0/8`、`169.254.0.0/16` 链路本地
 * （云厂商实例元数据 `169.254.169.254` 在其内）、TEST-NET-1/2/3（`192.0.2/24`、
 * `198.51.100/24`、`203.0.113/24`）、`198.18.0.0/15` 基准测试段、`224/4` 组播与
 * `240/4` 保留（含广播）；IPv6 侧未指定 `::`、链路本地 `fe80::/10`、组播 `ff00::/8`，
 * 以及内嵌 IPv4 的 `::ffff:x` 按内嵌地址递归判。
 *
 * **回环 / RFC1918 / CGNAT(100.64/10) / ULA(fc00::/7) 一律放行**：第七轮 B8 裁决
 * 「本机与内网必须能打开」是这条边界的上界，下一轮不得当 SSRF 缺陷反向收紧。
 * 元数据端点为什么仍在拒绝名单：它不是"访问内网设备"，而是 SSRF 取实例凭据的主路径。
 * 已知代价照抄 Windows 侧的账：阿里云元数据 `100.100.100.200` 落在放行的 CGNAT 段内。
 *
 * 为什么 Android 现在才需要它（R8-AD-03）：导航层的保留段由 Rust 核心判、子资源层的
 * 明文形态由本 app 的 NSC 挡住，但**下载**交系统 `DownloadProvider` 发请求——那是另
 * 一个进程，本 app 的 `network_security_config.xml` 管不到它。于是
 * `http://169.254.169.254/latest/user-data` 这类「明文 + 保留地址」在下载层完整绕过
 * 并落盘到公共下载目录。
 *
 * 两条刻意与孪生同口径的规则：
 * • **非 IP 主机名一律放行**（`my-nas.local`、`printer.internal`、hosts 映射名）——
 *   本函数零 DNS，名字权威在 DNS；且 Windows 同口径。
 * • **数字形态的非常规写法一律拒绝**（纯十进制整数、`0x` 十六进制、前导零八进制、
 *   段数不是 4 的简写）：Chromium 按 inet_aton 解释、Java/OS 给的是另一个结果
 *   （CS-348/AD-213 记过），两侧口径不同就是绕过面；真实主机名不会长这样，误伤面为零。
 *
 * host 的切分复用 [LocalTargetHosts.hostOf]——本仓不欢迎第二个 URL 解析器。
 *
 * 格式注记（不是审美问题）：下面三个 `when` 的条目都不带尾注。ktlint 把条目尾注算进
 * **下一条** condition 的前导注释，整块因此被判为「含多行 when-condition」并要求条目间
 * 加空行——第八轮两次红灯：先在条目后写注记被打红，改成条目间空行**仍**打红（注释照旧
 * 附着）。口径一律写在 KDoc 里，代码只承载判定。
 */
object ReservedAddressBoundary {
    /** 拒绝码单源（与 Windows `ReservedAddressBoundary.DenyCode` 同字面量）。 */
    const val DENY_CODE: String = "reserved_address"

    private const val IPV4_OCTETS = 4
    private const val OCTET_MAX_DIGITS = 3
    private const val UNSPECIFIED_FIRST = 0
    private const val LINK_LOCAL_FIRST = 169
    private const val LINK_LOCAL_SECOND = 254
    private const val TEST_NET_1_FIRST = 192
    private const val TEST_NET_1_SECOND = 0
    private const val TEST_NET_1_THIRD = 2
    private const val TEST_NET_2_FIRST = 198
    private const val TEST_NET_2_SECOND = 51
    private const val TEST_NET_2_THIRD = 100
    private const val TEST_NET_3_FIRST = 203
    private const val TEST_NET_3_SECOND = 0
    private const val TEST_NET_3_THIRD = 113
    private const val BENCHMARK_FIRST = 198
    private val BENCHMARK_SECOND = 18..19
    private const val MULTICAST_FROM = 224
    private const val HEX_PREFIX = "0x"
    private const val IPV4_MAPPED_PREFIX = "::ffff:"
    private const val UNSPECIFIED_IPV6 = "::"
    private const val HEX_RADIX = 16
    private const val IPV6_GROUP_MAX_DIGITS = 4
    private const val LINK_LOCAL_MASK = 0xFFC0 // fe80::/10 的前 10 位
    private const val LINK_LOCAL_BITS = 0xFE80
    private const val MULTICAST_MASK = 0xFF00 // ff00::/8 的前 8 位
    private const val MULTICAST_BITS = 0xFF00
    private const val HEX_DIGITS = "0123456789abcdef"

    /** URL 形态的入口（下载直链、`setDownloadListener` 给的就是它）。 */
    fun denies(url: String): Boolean = deniesHost(LocalTargetHosts.hostOf(url))

    /**
     * host 是否属"永不作为浏览/下载目标"的保留地址形态。条目顺序即口径：
     * ①切不出 host ⇒ 不可判定 ⇒ 不放行；②zone-id / 方括号残留不是设备地址；
     * ③含冒号交 [deniesIpv6]；④纯十进制整数、⑤`0x` 前缀——与 OS 解释分歧；
     * ⑥规范点分十进制交 [deniesIpv4]；⑦点分但形态不规范（段数≠4、前导零八进制、
     * 空段）同属分歧面；⑧其余是主机名 ⇒ 零 DNS，权威交 DNS。
     */
    fun deniesHost(rawHost: String): Boolean {
        val host = rawHost.trim().lowercase().trimEnd('.')
        return when {
            host.isEmpty() -> true
            host.contains('%') || host.contains('[') || host.contains(']') -> true
            host.contains(':') -> deniesIpv6(host)
            host.all { it.isDigit() } -> true
            host.startsWith(HEX_PREFIX) -> true
            isDecimalIpv4(host) -> deniesIpv4(octetsOf(host))
            hasNumericAuthority(host) -> true
            else -> false
        }
    }

    /**
     * IPv6 侧只拦三类：未指定 `::`、链路本地 `fe80::/10`、组播 `ff00::/8`。
     * `::ffff:x.y.z.w` 按内嵌 IPv4 递归判，内嵌段不合点分十进制同样拒（不可判定）；
     * 首组切不出来也拒。其余——回环 `::1`、ULA `fc00::/7`、全局单播——一律放行：
     * B8 裁决与 Windows 同口径。
     */
    private fun deniesIpv6(host: String): Boolean {
        val mapped = host.startsWith(IPV4_MAPPED_PREFIX)
        val embedded = host.removePrefix(IPV4_MAPPED_PREFIX)
        val firstGroup = firstGroupOf(host)
        return when {
            mapped -> !isDecimalIpv4(embedded) || deniesIpv4(octetsOf(embedded))
            host == UNSPECIFIED_IPV6 -> true
            firstGroup == null -> true
            else -> isReservedIpv6Head(firstGroup)
        }
    }

    /** `fe80::/10` 与 `ff00::/8` 都只落在首组的高位段上，不必解析整串。 */
    private fun isReservedIpv6Head(firstGroup: Int): Boolean =
        (firstGroup and LINK_LOCAL_MASK) == LINK_LOCAL_BITS ||
            (firstGroup and MULTICAST_MASK) == MULTICAST_BITS

    /** 首组数值（`::1` 这类省略前导零的写法按 0 算）；形态不合返回 null。 */
    private fun firstGroupOf(host: String): Int? {
        val group = host.substringBefore(':')
        return when {
            group.isEmpty() -> 0
            group.length > IPV6_GROUP_MAX_DIGITS || !group.all { it in HEX_DIGITS } -> null
            else -> group.toInt(HEX_RADIX)
        }
    }

    private fun isDecimalIpv4(host: String): Boolean {
        val parts = host.split('.')
        return parts.size == IPV4_OCTETS && parts.all { isDecimalOctet(it) }
    }

    private fun octetsOf(host: String): IntArray = host.split('.').map { it.toInt() }.toIntArray()

    /** 前导零（`0177`）是八进制形态，不当十进制接受——交 [hasNumericAuthority] 的分歧面拒。 */
    private fun isDecimalOctet(text: String): Boolean =
        text.isNotEmpty() && text.length <= OCTET_MAX_DIGITS && text.all { it.isDigit() } &&
            (text == "0" || !text.startsWith("0"))

    /**
     * 点分但形态不规范（段数≠4、前导零八进制、空段、`0x` 混写）：OS/Java 与
     * Chromium 的 inet_aton 解释不同（CS-348/AD-213 记过）⇒ 宁可拒下载。
     */
    private fun hasNumericAuthority(host: String): Boolean {
        val parts = host.split('.')
        return host.contains('.') && parts.all(::looksLikeOctetFragment)
    }

    private fun looksLikeOctetFragment(text: String): Boolean {
        if (text.isEmpty()) return true
        return text.all { it.isDigit() } || text.startsWith(HEX_PREFIX)
    }

    /**
     * 保留段表（条目顺序即口径）：`0/8` 未指定；`169.254/16` 链路本地（云元数据
     * `169.254.169.254` 在其内）；TEST-NET-1/2/3 文档段；`198.18.0.0/15` 基准测试段；
     * 末条 `b0 >= 224` 覆盖组播 `224/4`、`240/4` 保留与广播。
     */
    private fun deniesIpv4(octets: IntArray): Boolean {
        val b0 = octets[0]
        return when {
            b0 == UNSPECIFIED_FIRST -> true
            b0 == LINK_LOCAL_FIRST && octets[1] == LINK_LOCAL_SECOND -> true
            b0 == TEST_NET_1_FIRST && octets[1] == TEST_NET_1_SECOND && octets[2] == TEST_NET_1_THIRD -> true
            b0 == TEST_NET_2_FIRST && octets[1] == TEST_NET_2_SECOND && octets[2] == TEST_NET_2_THIRD -> true
            b0 == TEST_NET_3_FIRST && octets[1] == TEST_NET_3_SECOND && octets[2] == TEST_NET_3_THIRD -> true
            b0 == BENCHMARK_FIRST && octets[1] in BENCHMARK_SECOND -> true
            else -> b0 >= MULTICAST_FROM
        }
    }
}

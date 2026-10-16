package com.aegis.broker

/**
 * IP 字面量的**文本**解析（R9-B66 / 队列 Q4 第二半）——零 DNS、零平台依赖。
 *
 * 为什么不用 JDK 现成的：`InetAddress.getByName` 会做解析（CS-382 的 UI 冻结面就是这么
 * 来的）、还接受裸 IPv4；`IPAddressUtil` 是 `sun.*` 内部 API。而 `LocalTargetHosts` 的
 * 三条契约里有两条正是「纯字符串 + JVM 可测」，解析器必须自己写。
 * 从 `LocalTargetHosts` 拆出是 300 行红线逼的，不是审美：判据仍然只有一份，
 * 本文件只回答「这串文本是不是一个 IP、它是哪 16 个字节」，不负责分类。
 *
 * 接受的形态与孪生解析器逐条对齐（Rust `std::net::Ipv6Addr::from_str`、
 * Windows `IPAddress.TryParse`）：至多一处 `::`、每组 1-4 位十六进制（允许前导零）、
 * 末尾可挂一段点分 IPv4（占两组，段值 0-255 且无前导零）。
 *
 * 拒绝的形态（与 contracts 的 url-origin-invalid 同一批向量）：zone-id（`%`）、
 * 方括号残留、多处 `::`、悬空单冒号、段数超限、`.` 出现在非末组、
 * 点分尾段里的前导零八进制（`::ffff:0177.0.0.1`——AD-213 同源的分歧面）。
 */
internal object AddressText {
    /** 点分十进制段数与单段形态上限。 */
    internal const val IPV4_OCTETS = 4
    private const val OCTET_MAX_DIGITS = 3
    private const val OCTET_MAX = 255

    /** IPv6 的字节数/组数与单组形态。 */
    internal const val IPV6_BYTES = 16
    private const val IPV6_GROUPS = 8
    private const val BYTES_PER_GROUP = 2
    private const val GROUP_SHIFT = 8
    private const val OCTETS_PER_GROUP = 2
    private const val OCTET_MASK = 0xff
    private const val RADIX_HEX = 16
    private const val ZERO_GROUP = 0

    /** 解析器不接受的字符：作用域号分隔符与括号残留（括号由调用方剥）。 */
    private val FORBIDDEN_CHARS = charArrayOf('%', '[', ']')

    /** 悬空单冒号（`:1` / `1:`）；单独的 `:` 由 [hexGroups] 的空组段判拒。 */
    private val danglingColon = Regex("^:[^:]|[^:]:$")

    /** 单个十六进制组：1-4 位小写十六进制（调用方已把 host 小写）。 */
    private val hexGroup = Regex("[0-9a-f]{1,4}")

    /**
     * IPv6 文本 → 16 字节；非法形态返回 null。入参是**已剥方括号**的地址体。
     *
     * `::1` 与 `0:0:0:0:0:0:0:1` 必须得到同一份字节——分类只在字节上做。
     */
    internal fun ipv6ToBytes(body: String): ByteArray? {
        if (!isPlausibleIpv6Text(body)) return null
        return groupPlan(body)?.let { groups -> groupsToBytes(groups) }
    }

    /** 合法段 → 0..255，否则 -1。 */
    internal fun octetValueOrMinusOne(text: String): Int {
        val isPlainDecimal =
            text.length in 1..OCTET_MAX_DIGITS && text.all { it.isDigit() } && (text == "0" || !text.startsWith("0"))
        val value = if (isPlainDecimal) text.toInt() else OCTET_MAX + 1
        return if (value in 0..OCTET_MAX) value else -1
    }

    private fun isPlausibleIpv6Text(body: String): Boolean =
        body.isNotEmpty() && body.none { it in FORBIDDEN_CHARS } && hasOneCompression(body)

    /**
     * 压缩段基线：至多一处 `::`（两处以上时 `indexOf != lastIndexOf`，`:::` 同样落进
     * 这个判据）且不悬空。写成一个表达式而不是三条 `&&` 是为了少一个 detekt 判定点。
     */
    private fun hasOneCompression(body: String): Boolean =
        body.indexOf("::") == body.lastIndexOf("::") && !danglingColon.containsMatchIn(body)

    /** 文本 → 8 个 16 位组（内嵌 IPv4 占末两组）；形态不合返回 null。 */
    private fun groupPlan(body: String): List<Int>? {
        val quad = embeddedQuadGroups(body) ?: return null
        // 点分尾段切在哪一列：尾段**紧跟 `::`** 时（v4-compatible 写法
        // `::169.254.169.254`）两个冒号都得留在十六进制侧——切掉一个，`::` 就成了悬空的
        // 单个 `:`，压缩标记消失、整条地址读不出来。R9-B69 实测：Android 因此把这一形态
        // 判成语法非法，而核心与 .NET 都收下它。其余写法（`::ffff:x.y.z.w`、
        // `0:0:0:0:0:ffff:127.0.0.1`）的最后一个冒号就是尾段分隔符，照旧切在那儿。
        // 不拆成第六个函数：本对象的 detekt `thresholdInObjects: 11` 已被 R9-B66 用满。
        val lastColon = body.lastIndexOf(':')
        val compatibleTail = body.getOrNull(lastColon - 1) == ':'
        val tailOffset = if (compatibleTail) 1 else 0
        val cut = if (quad.isEmpty()) body.length else lastColon + tailOffset
        val hex = body.substring(0, cut)
        val compression = hex.indexOf("::")
        val head = hexGroups(if (compression < 0) hex else hex.substring(0, compression))
        val tail = if (compression < 0) emptyList() else hexGroups(hex.substring(compression + 2))
        return if (head == null || tail == null) null else withFill(compression, head, tail, quad)
    }

    /** 无压缩时必须正好 8 组；有压缩时 `::` 至少替一组（否则它是冗余写法）。 */
    private fun withFill(
        compression: Int,
        head: List<Int>,
        tail: List<Int>,
        quad: List<Int>,
    ): List<Int>? {
        val fill = IPV6_GROUPS - head.size - tail.size - quad.size
        val countFits = if (compression < 0) fill == 0 else fill > 0
        return if (fill >= 0 && countFits) head + List(fill) { ZERO_GROUP } + tail + quad else null
    }

    /**
     * 末尾点分 IPv4 → 两组。没有 `.` 是空表（纯十六进制形态）；`.` 出现在最后一个冒号
     * 之前（`1.2:3:4:…`）或整个地址没有冒号（`1.2.3.4`——方括号里的裸 IPv4 不是 IPv6）
     * 都是 null。
     */
    private fun embeddedQuadGroups(body: String): List<Int>? {
        val lastColon = body.lastIndexOf(':')
        val firstDot = body.indexOf('.')
        return when {
            firstDot < 0 -> emptyList()
            lastColon < 0 || firstDot < lastColon -> null
            else -> quadGroups(body.substring(lastColon + 1))
        }
    }

    private fun quadGroups(text: String): List<Int>? {
        val values = text.split('.').map { octetValueOrMinusOne(it) }
        if (values.size != IPV4_OCTETS || values.any { it < 0 }) return null
        return values.chunked(OCTETS_PER_GROUP).map { (high, low) -> (high shl GROUP_SHIFT) or low }
    }

    /** 冒号分隔的组序列 → 组值；空串是零组（`::` 的某一侧），空组段与超 4 位是 null。 */
    private fun hexGroups(text: String): List<Int>? {
        val parts = if (text.isEmpty()) emptyList() else text.split(':')
        return if (parts.all { hexGroup.matches(it) }) parts.map { it.toInt(RADIX_HEX) } else null
    }

    private fun groupsToBytes(groups: List<Int>): ByteArray {
        val bytes = ByteArray(IPV6_BYTES)
        groups.forEachIndexed { index, value ->
            bytes[index * BYTES_PER_GROUP] = ((value ushr GROUP_SHIFT) and OCTET_MASK).toByte()
            bytes[index * BYTES_PER_GROUP + 1] = (value and OCTET_MASK).toByte()
        }
        return bytes
    }
}

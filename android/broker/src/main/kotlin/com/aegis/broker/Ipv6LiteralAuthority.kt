package com.aegis.broker

/**
 * 地址栏输入的 IPv6 字面量判据与 URI 正典形态（第九轮 R9-B85 / 队列 Q68 裁决「判导航」）。
 *
 * 只回答一件事：这段文本的 authority 是不是**合法 IPv6 字面量**，是的话它的 URI 正典
 * （带方括号）整段怎么写。语法仍归 [AddressText]，本机/内网分类仍归 [LocalTargetHosts]。
 * 为什么需要本对象：app 侧此前只能看「拼写里有没有点」，而 IPv6 字面量按规则**不含点**，
 * 于是 `[::1]`、`[fd12::3]` 在 Android 被读成搜索词，同一条串在 Windows 却导航到本机服务——
 * 「同一个人在两台设备上敲同一串字符，一台打开、一台去搜索引擎」（Q68 登记时的原话）。
 * 裁决取「按地址族判」，本文件就是那条判据的落点；它不新增第三份 IPv6 语法。
 *
 * 接受的形态与 Windows `UrlNormalizer.IsIpv6Literal` ＋ `BracketIpv6` 同一条：
 * 方括号形态（可带 `:port`、`/path`），以及裸冒号起始（`::1`）——URI 正典要求方括号，
 * 裸形态在这里补括号，补完才谈得上 [LocalTargetHosts.hostOf]（它对裸多冒号形态返回空串，
 * 那是有意的 fail-closed：缺括号的裸 IPv6 不是 host:port 形态）。
 * 字母起始（`fe80::1`）不在本判据内：它读起来像 scheme，两端各自维持早退/拒绝。
 *
 * 拒绝的形态由 [AddressText.ipv6ToBytes] 决定（zone-id、多处 `::`、段数超限）。其中一条要
 * 单列：**方括号里的点分 IPv4**（`[8.8.8.8]`）没有冒号、不是 IPv6，而
 * `contracts/vectors/url-origin-invalid.json` 把「括号内嵌裸 IPv4」钉成双重解释面一律拒
 * ⇒ 它继续判搜索词，与本判据不打架（R9-B78 那条例外正是这条契约的输入层形态）。
 */
object Ipv6LiteralAuthority {
    /** authority 之后可能开始的三个分隔符（路径/查询/片段）。 */
    private val AUTHORITY_END = charArrayOf('/', '?', '#')

    /** TCP 端口最多 5 位数字（与 `SearchEngines.MAX_PORT_SEGMENT_LENGTH` 同一个理由）。 */
    private const val PORT_MAX_DIGITS = 5

    /**
     * 地址栏文本 → URI 正典整段（IPv6 authority 一定带方括号，端口/路径/片段原样留在其后）。
     * 不是 IPv6 字面量时返回 null。小写化只用于解析，输出保留调用方给的字符。
     */
    fun canonicalize(text: String): String? {
        val trimmed = text.trim()
        val boundary = trimmed.indexOfAny(AUTHORITY_END)
        val authority = if (boundary < 0) trimmed else trimmed.substring(0, boundary)
        val tail = if (boundary < 0) "" else trimmed.substring(boundary)
        return when {
            authority.startsWith("[") -> {
                if (isCanonicalBracketed(authority)) trimmed else null
            }

            authority.startsWith(":") -> {
                if (isIpv6AddressText(authority)) "[" + authority + "]" + tail else null
            }

            else -> {
                null
            }
        }
    }

    /**
     * 方括号形态：地址体必须可解析，且 `]` 之后只允许一个 `:端口`——
     * `[::1]x` 这类尾巴不是 IPv6 authority（`contracts/vectors/url-origin-invalid.json`
     * 里有同名向量把「`]` 之后只允许 `:port`」钉成核心契约）。不这么收的话本端会判
     * 网址、Windows 却因为 `Uri.TryCreate` 失败判搜索词，正是要消灭的那类分叉。
     */
    private fun isCanonicalBracketed(authority: String): Boolean {
        val close = authority.indexOf(']')
        if (close < 2) return false
        val body = authority.substring(1, close)
        val tail = authority.substring(close + 1)
        return isIpv6AddressText(body) && (tail.isEmpty() || isPortSuffix(tail))
    }

    /** `]` 之后的端口尾巴：`:` 加 1-5 位十进制数字（上限见 [PORT_MAX_DIGITS]）。 */
    private fun isPortSuffix(tail: String): Boolean {
        if (!tail.startsWith(":")) return false
        val digits = tail.substring(1)
        return digits.isNotEmpty() && digits.length <= PORT_MAX_DIGITS && digits.all { it.isDigit() }
    }

    /** 文本是不是一个可解析的 IPv6 地址（解析器与分类层共用 [AddressText] 那一份）。 */
    private fun isIpv6AddressText(body: String): Boolean = AddressText.ipv6ToBytes(body.lowercase()) != null
}

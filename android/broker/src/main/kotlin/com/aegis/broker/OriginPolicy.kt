package com.aegis.broker

/**
 * 阶段 D（蓝图 android/broker/policy）：Origin/URL 策略——与 contracts
 * url-origin-valid/invalid 向量一致（http/https 放行——data:/blob:/javascript:/
 * userinfo/控制字符/无 host/超长拒绝——P0-01 同语义）。
 */
object OriginPolicy {
    private const val MAX_URL_LENGTH = 8192

    /** TCP 端口上限（RFC 6335——A-3 跨端口径对齐：越界拒绝）。 */
    private const val MAX_PORT = 65535

    /** 点分十进制 IPv4 段数（段数≠4 且全数字 = 备用编码，拒绝）。 */
    private const val IPV4_SEGMENT_COUNT = 4

    /** AD-299：IPv4 八位组上限（WHATWG 口径——逐段 ≤255，越界拒绝）。 */
    private const val IPV4_OCTET_MAX = 255

    /** 解析外部 URL（仅 http/https——非法返回 null——fail-closed）。 */
    fun tryParseExternal(raw: String?): java.net.URI? {
        if (raw.isNullOrBlank() || raw.length > MAX_URL_LENGTH) return null
        // T2 修复（全面审计批次2 2026-09-04）：归一层（SearchEngines
        // normalizeInput）放行精确 about:blank，但本函数只认 http/https →
        // broker 必拒——用户输 about:blank 得到误导性报错（自相矛盾死路径）。
        // 仅放行精确 about:blank（trim + 大小写不敏感）；about:evil 等
        // 其他 about 变体仍拒绝。
        if (raw.trim().equals("about:blank", ignoreCase = true)) {
            return java.net.URI("about:blank")
        }
        if (raw.any(::isControlChar)) return null
        val uri =
            try {
                java.net.URI(raw)
            } catch (e: Exception) {
                return null
            }
        val scheme = uri.scheme?.lowercase() ?: return null
        if (scheme != "http" && scheme != "https") return null
        if (uri.rawUserInfo != null) return null
        if (uri.host.isNullOrBlank()) return null
        // A-3 对齐（跨端口径）：java.net.URI 不校验端口上限——99999 这类
        // 越界端口 Rust origin.rs/Python security.py 均拒绝，此处显式对齐
        if (uri.port > MAX_PORT) return null
        // AD-299（P2，2026-10-02 审计）：端口 0 拒绝——Rust origin.rs（PY-075
        // 向量同口径）对 port_num == 0 fail-closed（保留端口不可用作目标），
        // java.net.URI 原样放行 port=0，此处对齐（-1 = 未写端口，保持放行）。
        if (uri.port == 0) return null
        // PY-071/072（审计 2026-09-25）：非点分十进制 IPv4 编码拒绝——整数/
        // 0x 十六进制/简写（127.1）OS 解析器均接受，双重解释混淆面——与
        // Rust origin.rs / C# OriginPolicy 口径一致
        val host = uri.host!!.lowercase()
        // AD-252（P1，2026-10-01 审计）：尾点 host（`localhost.` / `aegis.local.`）
        // 拒绝——java.net.URI 保留尾点原样放行，而 Chromium 归一化剥除尾点后
        // `location.hostname` 命中 bridge_guard 白名单（localhost/aegis.local）
        // 成为 trustedCaller；canonicalOrigin 又会产出幻影 origin
        // （https://localhost.）绑进 AuthorizedAction。本层是全链唯一能以
        // URI 原始形态观察到尾点的收口点——备用编码判定之前整链 fail-closed。
        if (host.endsWith(".")) return null
        // AD-299（P2，2026-10-02 审计）：host 校验对齐 Rust origin.rs RS-012——
        // ①字符集白名单 [a-z0-9.-]（xn-- punycode 在集内；下划线/引号等
        // DNS 不安全字符拒绝，PY-074 向量）；②前导点（空首标签）与 `..`
        // （连续点/空标签）拒绝（PY-073 向量——多数形态 java.net.URI 已折
        // host=null，此处显式收口防解析器漂移）；③`[` 拒绝——java.net.URI
        // 对 IPv6 字面量保留方括号原样放行（host="[::1]"），Rust 对 authority
        // 方括号形态一律拒绝（PY-069/070 向量）。
        if (host.startsWith(".") || host.contains("..") || host.contains("[")) return null
        if (!host.all { it in 'a'..'z' || it.isDigit() || it == '.' || it == '-' }) return null
        if (isAlternateIpv4Encoding(host)) return null
        return uri
    }

    /**
     * PY-071/072（审计 2026-09-25）：非点分十进制 IPv4 编码检测——整数/
     * 0x 十六进制/简写（127.1）OS 解析器均接受，双重解释混淆面统一拒绝；
     * 点分四段（合法 IPv4）保留。与 Rust origin.rs / C# OriginPolicy 口径一致。
     *
     * AD-213（2026-09-26 审计）：补两类漏判——①前导零八进制：`0177.0.0.1`
     * 四段全数字即放行，但 inet_aton 按八进制解释 = 127.0.0.1；②`0x` 逐段
     * 判定：`0x7f.1` 整串 startsWith("0x") 因含 `.` 判 false。Chromium 解析
     * 归一后 location.hostname 可命中 bridge_guard 白名单 127.0.0.1。
     */
    private fun isAlternateIpv4Encoding(host: String): Boolean {
        val segments = host.split('.')
        // 0x 逐段：任一段为十六进制编码（0x 前缀 + 至少一位十六进制字符）
        val hasHexSegment =
            segments.any { seg ->
                seg.length > 2 && seg.startsWith("0x") && seg.drop(2).any { it.isDigit() || it in 'a'..'f' }
            }
        // 前导零八进制：纯数字段长度>1 且以 0 开头（如 0177——十进制视角无害
        // 但 inet_aton 系解析栈按八进制解释）
        val hasLeadingZeroSegment =
            segments.any { seg -> seg.length > 1 && seg.startsWith('0') && seg.all { it.isDigit() } }
        // 简写/整数形态：全数字但非四段（127.1、2130706433）
        val isShorthand = segments.all { it.isNotEmpty() && it.all { c -> c.isDigit() } }
        // AD-299（P2，2026-10-02 审计）：四段全数字时逐段 ≤255——对齐 Rust
        // RS-228（WHATWG IPv4 解析器口径）。此前只看段数，999.1.1.1 /
        // 256.0.0.1 等八位组越界形态混过（跨端向量 RS-228 三条）。
        // 超长纯数字段（toInt 溢出）必然越界——按拒绝处理（fail-closed）。
        if (segments.size == IPV4_SEGMENT_COUNT && isShorthand) {
            if (segments.any { (it.toIntOrNull() ?: IPV4_OCTET_MAX + 1) > IPV4_OCTET_MAX }) return true
        }
        return hasHexSegment || hasLeadingZeroSegment ||
            (isShorthand && segments.size != IPV4_SEGMENT_COUNT)
    }

    /** 控制字符 / 空白判定（userinfo 注入与拆分混淆面——fail-closed）。 */
    private fun isControlChar(c: Char): Boolean = c.code < 0x20 || c.code == 0x7f || c.isWhitespace()
}

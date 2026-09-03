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
        if (raw.any { it.code < 0x20 || it.code == 0x7f || it.isWhitespace() }) return null
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
        return uri
    }
}

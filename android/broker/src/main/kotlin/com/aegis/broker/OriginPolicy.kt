package com.aegis.broker

/**
 * 阶段 D（蓝图 android/broker/policy）：Origin/URL 策略——与 contracts
 * url-origin-valid/invalid 向量一致（http/https 放行——data:/blob:/javascript:/
 * userinfo/控制字符/无 host/超长拒绝——P0-01 同语义）。
 */
object OriginPolicy {

    private const val MAX_URL_LENGTH = 8192

    /** 解析外部 URL（仅 http/https——非法返回 null——fail-closed）。 */
    fun tryParseExternal(raw: String?): java.net.URI? {
        if (raw.isNullOrBlank() || raw.length > MAX_URL_LENGTH) return null
        if (raw.any { it.code < 0x20 || it.code == 0x7f || it.isWhitespace() }) return null
        val uri = try {
            java.net.URI(raw)
        } catch (e: Exception) {
            return null
        }
        val scheme = uri.scheme?.lowercase() ?: return null
        if (scheme != "http" && scheme != "https") return null
        if (uri.rawUserInfo != null) return null
        if (uri.host.isNullOrBlank()) return null
        return uri
    }
}

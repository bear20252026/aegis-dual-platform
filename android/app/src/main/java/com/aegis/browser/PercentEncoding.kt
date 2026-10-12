package com.aegis.browser

/**
 * 严格百分号解码（R9-B33 / Q9 单源化）。
 *
 * 为什么要单源：这条规则此前只长在 `WebViewDownloadHandler` 里（AD-263 为 RFC 5987
 * 文件名而写），`DownloadPolicy` 的路径段与查询值解码另走 `java.net.URLDecoder`——
 * 同一个「URL 路径段」两套解码器，而前者 KDoc 正是后者的反驳理由（`URLDecoder` 按
 * query 语义把 `+` 解成空格，路径里的 `+` 是字面加号）。Windows 侧两处都是
 * `Uri.UnescapeDataString`（严格 `%XX`，不动 `+`），所以「严格」才是两端的公共口径。
 *
 * 语义边界：`+` 保持字面；`%XX` 不足两位十六进制按字面 `%` 处理；多字节字符的
 * `%E6%8A%A5` 序列作为字节流整体按 UTF-8 解码（不按单字节劈开）；解出非法 UTF-8
 * 序列原样返回（fail-closed——仍参与危险扩展判定，不因解码失败而放行）。
 */
internal object PercentEncoding {
    private const val UTF8_MAX_BYTES_PER_CHAR = 4

    private const val HEX_RADIX_OFFSET = 10

    private const val HEX_NIBBLE_SHIFT = 4

    private const val PERCENT_ESCAPE_LENGTH = 3

    /** 逐 `%XX` 还原字节流后整体按 UTF-8 解码；非法编码原样返回。 */
    fun decodeStrict(raw: String): String {
        // 字面字符按 UTF-8 展开最多 4 字节/字符——按上界分配
        val bytes = ByteArray(raw.length * UTF8_MAX_BYTES_PER_CHAR)
        var length = 0
        var i = 0
        while (i < raw.length) {
            val escapedByte = hexEscapeByteAt(raw, i)
            if (escapedByte != null) {
                bytes[length++] = escapedByte
                i += PERCENT_ESCAPE_LENGTH
            } else {
                val literal = raw[i].toString().toByteArray(Charsets.UTF_8)
                literal.forEach { bytes[length++] = it }
                i++
            }
        }
        return try {
            Charsets.UTF_8
                .newDecoder()
                .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(bytes, 0, length))
                .toString()
        } catch (_: java.nio.charset.CharacterCodingException) {
            raw
        }
    }

    /** 位置 [index] 起的 `%XX` 转义字节；非完整十六进制转义返回 null。 */
    private fun hexEscapeByteAt(
        raw: String,
        index: Int,
    ): Byte? {
        val high = hexValue(raw.getOrNull(index + 1))
        val low = hexValue(raw.getOrNull(index + 2))
        return if (raw[index] == '%' && high != null && low != null) {
            ((high shl HEX_NIBBLE_SHIFT) or low).toByte()
        } else {
            null
        }
    }

    /** 单字符十六进制值；非十六进制返回 null。 */
    private fun hexValue(c: Char?): Int? =
        if (c == null) {
            null
        } else {
            when (c) {
                in '0'..'9' -> c - '0'
                in 'a'..'f' -> c - 'a' + HEX_RADIX_OFFSET
                in 'A'..'F' -> c - 'A' + HEX_RADIX_OFFSET
                else -> null
            }
        }
}

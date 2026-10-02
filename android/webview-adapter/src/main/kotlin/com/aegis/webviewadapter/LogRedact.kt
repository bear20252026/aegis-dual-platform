package com.aegis.webviewadapter

/**
 * 日志脱敏（AD-004，2026-09-23 审计——Windows P37 对齐）：导航/错误/SafeBrowsing
 * 日志此前明文记录完整 URL（含 query 的 token/搜索词）。统一在日志面剥除
 * query 与 fragment，仅保留 scheme+host+path 以供排障。
 * 纯 JVM 可测——不依赖 android API。
 *
 * AD-220（2026-09-26 审计）：internal → public——下载拦截日志（app 模块
 * WebViewDownloadHandler）同样明文记录完整 URL（含 query），此前 internal
 * 可见性使 app 模块无法复用本单源（脱敏口径不得双源漂移）。
 */
object LogRedact {
    /** AD-264：scheme 分隔符（authority 起点定位）。 */
    private const val SCHEME_DELIMITER = "://"

    /** AD-264：userinfo 脱敏占位符。 */
    private const val REDACTED_USERINFO = "***@"

    /**
     * AD-264（2026-10-01 审计）：先剥 userinfo 再截 query——原实现
     * `https://token@host/path?q=1` 脱敏后仍保留 `token@host`（凭据完整
     * 入 logcat）。authority 段内 `@` 前的 userinfo 整体替换为 `***@`。
     */
    fun redact(url: String?): String {
        if (url.isNullOrEmpty()) return "<null>"
        val noQueryOrFragment = url.substringBefore('#').substringBefore('?')
        return stripUserInfo(noQueryOrFragment) + "…"
    }

    /** AD-264：authority 段 userinfo 剥除（纯字符串——JVM 可测）。 */
    private fun stripUserInfo(url: String): String {
        val schemeEnd = url.indexOf(SCHEME_DELIMITER)
        val authorityStart = schemeEnd + SCHEME_DELIMITER.length
        val authorityEnd = url.indexOf('/', authorityStart).takeIf { it >= 0 } ?: url.length
        val userInfoSeparator = url.lastIndexOf('@', authorityEnd - 1)
        return if (schemeEnd < 0 || userInfoSeparator < authorityStart) {
            url
        } else {
            url.substring(0, authorityStart) + REDACTED_USERINFO + url.substring(userInfoSeparator + 1)
        }
    }
}

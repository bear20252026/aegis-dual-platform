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
    fun redact(url: String?): String {
        if (url.isNullOrEmpty()) return "<null>"
        return url
            .substringBefore('#')
            .substringBefore('?') + "…"
    }
}

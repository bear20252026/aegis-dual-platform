package com.aegis.browser

/**
 * AD-103（审计 2026-09-23 清单·A6 批）：日志净化单源——BrowserViewModel
 * 标题净化与 AegisHomeBridge 消息净化此前各持一份相同实现（换行/回退/制表
 * 压平 + 截断），属同一安全口径的双源漂移面（页面/远端可控文本经换行可
 * 伪造多行 logcat 记录）。收敛为本单源。
 */
internal object LogSanitize {
    /** 压平换行/回退/制表 + 截断（[maxLength] 防日志洪泛）。 */
    fun flatten(
        message: String,
        maxLength: Int,
    ): String = message.replace(Regex("[\\r\\n\\t]+"), " ").take(maxLength)
}

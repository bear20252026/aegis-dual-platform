package com.aegis.browser

/**
 * AD-103（审计 2026-09-23 清单·A6 批）：日志净化单源——BrowserViewModel
 * 标题净化与 AegisHomeBridge 消息净化此前各持一份相同实现（换行/回退/制表
 * 压平 + 截断），属同一安全口径的双源漂移面（页面/远端可控文本经换行可
 * 伪造多行 logcat 记录）。收敛为本单源。
 *
 * AD-286（2026-10-01 审计）：压平面扩为全控制字符集 \p{Cntrl}（C0 0x00-0x1F
 * + DEL 0x7F + C1 0x80-0x9F）——原实现只压 \r\n\t，其余 C0（含 ESC 0x1B
 * 终端控制序列载体）原样入 logcat，ANSI 转义序列可在终端消费者侧伪造
 * 输出/清屏注入。
 */
internal object LogSanitize {
    /**
     * 压平全部控制字符 + 截断（[maxLength] 防日志洪泛）。
     *
     * 显式码位区间而非 \p{Cntrl}：Java 正则的 \p{Cntrl} 只覆盖
     * [\x00-\x1F\x7F]，不含 C1（0x80-0x9F，U+0085 NEL 等）——显式区间
     * 把 C1 一并纳入压平面。
     *
     * AD-308（2026-10-02 审计）：截断复用 [takeAtCharBoundary]（共享 internal
     * 顶层函数）——原 String.take 按 UTF-16 char 劈切，切点落在增补字符
     * （emoji 等）中间产生孤立代理对（logcat 渲染 � 且 length 语义失真；
     * 与 ReaderMode/BrowserEngine 截断同病）。
     */
    fun flatten(
        message: String,
        maxLength: Int,
    ): String = takeAtCharBoundary(message.replace(Regex("[\\u0000-\\u001F\\u007F-\\u009F]+"), " "), maxLength)
}

package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * AD-286（2026-10-01 审计）：日志净化控制字符全集向量——原 flatten 只压
 * \r\n\t，其余 C0（含 ESC 0x1B 终端转义载体）原样入 logcat。锁定向量：
 * C0 全集逐项、DEL、C1 采样、原有 \r\n\t 语义、连续控制字符合并、截断。
 */
class LogSanitizeTest {
    @Test
    fun everyC0ControlCharIsFlattened() {
        for (code in 0x00..0x1F) {
            val ch = code.toChar()
            if (ch == ' ') continue // 0x20 不在 C0（循环上界 0x1F 防御性跳过）
            assertEquals(
                "C0 控制字符 0x%02X 必须压平".format(code),
                "a b",
                LogSanitize.flatten("a${ch}b", 100),
            )
        }
    }

    @Test
    fun delAndC1ControlCharsAreFlattened() {
        assertEquals("a b", LogSanitize.flatten("a\u007Fb", 100))
        // C1（U+0080..U+009F）采样：APC/C1 控制字符同口径压平
        assertEquals("a b", LogSanitize.flatten("a\u0085b", 100))
        assertEquals("a b", LogSanitize.flatten("a\u009Fb", 100))
    }

    @Test
    fun escIsFlattenedNotPassedThrough() {
        // AD-286 主向量：ESC + CSI 序列（ANSI 转义）不得入 logcat
        val flattened = LogSanitize.flatten("a\u001B[31mred", 100)
        assertEquals(false, flattened.contains("\u001B"))
        assertEquals("a [31mred", flattened)
        assertEquals(false, LogSanitize.flatten("\u001B[2J清屏", 100).contains("\u001B"))
    }

    @Test
    fun legacyWhitespaceSemanticsPreserved() {
        assertEquals("a b", LogSanitize.flatten("a\r\nb", 100))
        assertEquals("a b", LogSanitize.flatten("a\tb", 100))
        // 连续控制字符合并为单个空格
        assertEquals("a b", LogSanitize.flatten("a\r\n\t\u0000b", 100))
    }

    @Test
    fun truncationStillAppliesAfterFlattening() {
        assertEquals("ab", LogSanitize.flatten("abc", 2))
        // 压平先于截断：控制字符不占截断预算后的可见位
        assertEquals("a b", LogSanitize.flatten("a\nbcdef", 3))
    }

    @Test
    fun plainTextPassesThroughUnchanged() {
        assertEquals("正常日志消息 no controls", LogSanitize.flatten("正常日志消息 no controls", 100))
    }
}

package com.aegis.diagnostics

/**
 * 阶段 D（蓝图 android/diagnostics）：脱敏诊断日志骨架——不记录 token/网页内容/
 * query secret（蓝图迁移表：event_log/crash_reporter 迁入——脱敏、速率限制）。
 * 阶段 D 最小——非敏感健康/崩溃信息（完整实现按蓝图迭代）。
 */
class Diagnostics {
    private val log = mutableListOf<String>()

    fun logNonSensitive(message: String) {
        // 只记录非敏感信息（不包含 token/网页内容/query secret——脱敏）
        log += "${java.time.Instant.now()} $message"
    }

    val entries: List<String> get() = log
}

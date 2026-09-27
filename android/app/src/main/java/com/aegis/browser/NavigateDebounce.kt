package com.aegis.browser

/**
 * AD-103 配套（审计 2026-09-23 清单·A6 批）：导航防抖独立小类——自
 * BrowserViewModel 抽出（P2 修复，全量复审 2026-09-01）：待审批确认期间
 * 忽略重复提交（连点会撤销待确认 nonce 并触发误导性提示）；
 * [intervalMs] 内重复点击忽略。时刻取 SystemClock.uptimeMillis（单调）。
 * 单出口无提前 return（detekt ReturnCount）。
 */
internal class NavigateDebounce(
    private val intervalMs: Long,
) {
    private var lastAttemptAt = 0L

    /** 是否放行本次导航尝试；放行即记录锚点。[pendingConfirmationActive]
     *  = 待审批确认挂起中（此时一律不放行）。 */
    fun ok(pendingConfirmationActive: Boolean): Boolean {
        val elapsed = android.os.SystemClock.uptimeMillis() - lastAttemptAt
        val allowed = !pendingConfirmationActive && elapsed >= intervalMs
        if (allowed) lastAttemptAt = android.os.SystemClock.uptimeMillis()
        return allowed
    }
}

package com.aegis.browser

/**
 * AD-103 配套（审计 2026-09-23 清单·A6 批）：导航防抖独立小类——自
 * BrowserViewModel 抽出（P2 修复，全量复审 2026-09-01）：待审批确认期间
 * 忽略重复提交（连点会撤销待确认 nonce 并触发误导性提示）；
 * [intervalMs] 内重复点击忽略。单出口无提前 return（detekt ReturnCount）。
 *
 * AD-157（审计 2026-09-23 清单·A7 批）：时钟注入——单调时刻经 [now] 供给，
 * 默认取 SystemClock.uptimeMillis（单调时钟）。原实现时钟硬编码，防抖窗口
 * 行为（窗口边界/待审批抑制/锚点推进）完全不可 JVM 单测；注入后
 * NavigateDebounceTest 以假时钟逐毫秒驱动窗口语义。
 */
internal class NavigateDebounce(
    private val intervalMs: Long,
    private val now: () -> Long = { android.os.SystemClock.uptimeMillis() },
) {
    private var lastAttemptAt = 0L

    /** 是否放行本次导航尝试；放行即记录锚点。[pendingConfirmationActive]
     *  = 待审批确认挂起中（此时一律不放行，且不推进锚点——挂起期间不
     *  消耗防抖窗口）。 */
    fun ok(pendingConfirmationActive: Boolean): Boolean {
        val elapsed = now() - lastAttemptAt
        val allowed = !pendingConfirmationActive && elapsed >= intervalMs
        if (allowed) lastAttemptAt = now()
        return allowed
    }
}

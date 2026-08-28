package com.aegis.chromeui

/**
 * 阶段 D（蓝图 android/chrome-ui）：Browser/Tab 生命周期显式状态机（sealed interface
 * ——避免 callback"记录但继续"——安全默认值）。与 contracts 决策一致——
 * 状态转移由 broker 授权（ADR-002——没有 AuthorizedAction 不能进入副作用）。
 */
sealed interface BrowserState {
    /** 活跃（前台——当前标签导航/渲染）。 */
    data object Active : BrowserState

    /** 后台（暂停——WebView onPause——JS timers 暂停——TabManager suspendAll）。 */
    data object Background : BrowserState

    /** 挂起（LRU——资源释放——非活跃标签）。 */
    data object Suspended : BrowserState

    /** 恢复中（进程重建——URL 经 broker 策略重验后恢复——不自动放行）。 */
    data object Restoring : BrowserState

    /** 崩溃（onRenderProcessGone——标记崩溃——销毁/重建 WebView——熔断）。 */
    data object Crashed : BrowserState

    /** 已关闭。 */
    data object Closed : BrowserState
}

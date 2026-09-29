package com.aegis.browser

import android.webkit.WebView
import com.aegis.broker.ApprovalRequest
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.time.Instant

/**
 * AD-103（审计 2026-09-23 清单·A6 批）：浏览器 UI 状态模型单文件——
 * PendingNavigationConfirmation / PageError / HistoryAction 此前内嵌在
 * BrowserViewModel.kt 文件尾部，随文件膨胀（676 行超改造红线 500）一并
 * 抽出；BrowserViewModel 只保留状态机与意图入口。
 *
 * 仅 ViewModel 保存发起 WebView 引用；Compose 仅显示 request 的最小绑定字段。
 */
data class PendingNavigationConfirmation internal constructor(
    internal val webView: WebView,
    val request: ApprovalRequest,
)

/**
 * P2-1 修复（全面审计 2026-09-04）：页面级错误（不可变数据类）。
 *
 * @param description 简短中文错误说明（错误面板主文案）
 * @param isSsl       是否为 SSL 证书错误（面板标题区分「安全连接失败」）
 * @param url         出错页面的 URL（面板展示定位）
 * @param webView     AD-215（2026-09-26 审计）：错误归属标签的 WebView 引用
 *                    ——切换/关闭标签时按当前标签对账清除（错误遮罩不得
 *                    跨标签残留）。
 */
data class PageError(
    val description: String,
    val isSsl: Boolean,
    val url: String,
    internal val webView: WebView,
)

/** 历史导航动作。 */
enum class HistoryAction { BACK, FORWARD, RELOAD }

/**
 * AD-152（审计 2026-09-23 清单·A7 批）：标签栏布局位置枚举——ViewModel 与
 * MainActivity 此前以魔法字符串 "top"/"left" 传递/比较布局态（typo 即静默
 * 走默认分支，编译器无感知）。收敛为类型安全的枚举单源；视觉文案与
 * 持久化（如未来落地）不再依赖裸字符串。
 */
enum class TabsPosition { TOP, LEFT }

/** 装配点对「可空布尔」统一折叠为 false 的惯用收口（原 BrowserViewModel 文件私有）。 */
internal fun Boolean?.orFalse(): Boolean = this ?: false

/**
 * AD-110（审计 2026-09-23 清单·A6 批）：审批对话框过期时刻的用户可读格式化。
 * Instant.toString() 输出 ISO-8601（如 2026-09-27T04:30:00Z），用户不可读——
 * 格式化为系统时区 `yyyy-MM-dd HH:mm`。minSdk 26 可用 java.time；kotlinx
 * Instant 经 epoch 秒桥接（二者均为 UTC 时刻语义）。
 */
internal object ExpiryFormat {
    private val FORMATTER: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

    /** [zone] 仅供 JVM 单测注入固定时区；生产走系统默认。 */
    fun format(
        instant: Instant,
        zone: ZoneId = ZoneId.systemDefault(),
    ): String =
        java.time.LocalDateTime
            .ofInstant(java.time.Instant.ofEpochSecond(instant.epochSeconds), zone)
            .format(FORMATTER)
}

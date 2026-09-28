package com.aegis.browser

import android.webkit.WebView

/**
 * 单个浏览器标签的数据模型（单文件单职责：只描述标签状态）。
 *
 * 每个标签持有自己的 [WebView] 实例，切换标签时通过显示/隐藏保留
 * 各页面状态（不销毁）。[suspended] 表示该标签的 WebView 已被挂起
 * （内存压力时由 TabManager 调用），挂起期间不接收绘制/事件。
 *
 * AD-082/083（2026-09-26 审计）：删除 pinned/group 字段——全工程零写入点的
 * 「假 parity」（Windows 端有置顶/工作区交互，Android 端从未接线：📌 前缀
 * 与分组标题永远渲染静态默认值）。字段随真实功能（置顶/工作区 UI 及写入点）
 * 一起回归，不在数据层预留死形态。
 *
 * AD-084（2026-09-26 审计）：字段全部 val——写路径经 TabManager copy 替换
 * 实例（StateFlow 依赖 equals 感知变化），消灭原地改 var 的静默失联面。
 *
 * @param id        全局唯一标签 ID（由 TabManager 分配）
 * @param title     标签标题（WebView 加载完成后回填）
 * @param url       当前地址
 * @param webView   该标签独占的 WebView（不可为空）
 * @param suspended 是否已挂起（非活跃且被 TabManager 挂起时为 true）
 * @param lastUsed  最近使用时刻（SystemClock.elapsedRealtime 单调毫秒——
 *                  AD-079：LRU 挂起策略弃用墙钟，防用户改时间/NTP 回拨打乱挂起次序）
 */
data class Tab(
    val id: Long,
    val title: String,
    val url: String,
    val webView: WebView,
    val suspended: Boolean = false,
    val lastUsed: Long = 0,
)

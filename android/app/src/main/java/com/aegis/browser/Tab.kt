package com.aegis.browser

import android.webkit.WebView

/**
 * 单个浏览器标签的数据模型（单文件单职责：只描述标签状态）。
 *
 * 每个标签持有自己的 [WebView] 实例，切换标签时通过显示/隐藏保留
 * 各页面状态（不销毁）。[suspended] 表示该标签的 WebView 已被挂起
 * （内存压力时由 TabManager 调用），挂起期间不接收绘制/事件。
 *
 * @param id       全局唯一标签 ID（由 TabManager 分配）
 * @param title    标签标题（WebView 加载完成后回填）
 * @param url      当前地址
 * @param webView  该标签独占的 WebView（不可为空）
 * @param suspended 是否已挂起（非活跃且被 TabManager 挂起时为 true）
 */
data class Tab(
    val id: Long,
    var title: String,
    var url: String,
    val webView: WebView,
    var suspended: Boolean = false,
)

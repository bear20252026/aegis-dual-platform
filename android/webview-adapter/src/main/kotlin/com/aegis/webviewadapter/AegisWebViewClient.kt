package com.aegis.webviewadapter

import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.aegis.broker.AndroidBroker
import com.aegis.broker.Decision

/**
 * 阶段 D（蓝图 android/webview-adapter）：WebViewClient 封装——只把 WebView 回调
 * 转换为请求（不拥有安全策略——ADR-002）。导航/新窗口经 broker 决策（真实拒绝）；
 * onRenderProcessGone 返回 true + 清理 WebView（官方 Termination Handling API——
 * 不返回 true 则系统 kill Activity——调研交叉确认）。
 */
class AegisWebViewClient(
    private val broker: AndroidBroker,
    private val sessionId: String,
    private val onRendererGone: (WebView) -> Unit,
) : WebViewClient() {

    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val decision = broker.evaluateNavigation(sessionId, "tab-0", 0L, request.url.toString(), "navigation")
        return decision is Decision.Deny  // true = 拦截（拒绝导航）
    }

    override fun onRenderProcessGone(view: WebView, detail: android.webkit.RenderProcessGoneDetail): Boolean {
        // 官方 Termination Handling API：返回 true（不默认 kill Activity）——
        // 移除 WebView 实例/不重用（调研：检查+重建+恢复现场——返回 true 是硬编码要求）
        onRendererGone(view)
        return true
    }
}

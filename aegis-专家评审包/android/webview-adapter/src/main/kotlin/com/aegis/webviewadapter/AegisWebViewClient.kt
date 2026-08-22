package com.aegis.webviewadapter

import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.aegis.broker.AndroidBroker
import com.aegis.broker.Decision
import android.webkit.SafeBrowsingResponse

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

    /** 用户手动放行的 HTTP 域名（会话内有效——照搬 voidbrowser https_only）。 */
    private val allowedHttpDomains = mutableSetOf<String>()

    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val url = request.url.toString()
        val scheme = request.url.scheme ?: ""
        val host = request.url.host ?: ""

        // ① HTTPS-only 检查（照搬 voidbrowser HttpsOnlyState——HTTP→HTTPS 升级）
        if (scheme == "http" && host !in allowedHttpDomains) {
            val upgraded = url.replaceFirst("http://", "https://")
            android.util.Log.i("Aegis", "HTTPS-only: 升级 $url → $upgraded")
            view.loadUrl(upgraded)
            return true  // 拦截原 HTTP 请求
        }

        // ② Broker 决策（单路径收敛——专家审计）
        val decision = broker.evaluateNavigation(sessionId, "tab-0", 0L, url, "navigation")
        return decision is Decision.Deny  // true = 拦截（拒绝导航）
    }

    /** 用户手动放行 HTTP 域名（会话内有效）。 */
    fun allowHttpDomain(domain: String) {
        allowedHttpDomains.add(domain)
    }

    override fun onRenderProcessGone(view: WebView, detail: android.webkit.RenderProcessGoneDetail): Boolean {
        onRendererGone(view)
        return true
    }

    // 安全回调（从 BrowserEngine.configure() 移入——单路径收敛——专家审计）：
    // Safe Browsing 命中默认阻断（不继续到恶意页）+ 审计记录
    override fun onSafeBrowsingHit(
        view: WebView,
        request: WebResourceRequest,
        threatType: Int,
        callback: SafeBrowsingResponse,
    ) {
        callback.backToSafety(true)
        android.util.Log.w("Aegis", "SafeBrowsing 命中阻断: ${request.url} threatType=$threatType")
    }
}

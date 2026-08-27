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
    private val tabId: String,
    private val onRendererGone: (WebView) -> Unit,
) : WebViewClient() {

    /** 用户手动放行的 HTTP 域名（会话内有效——照搬 voidbrowser https_only）。 */
    private val allowedHttpDomains = mutableSetOf<String>()
    private var documentGeneration = 0L

    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val requestedUrl = request.url.toString()
        val securedUrl = upgradeToHttpsIfNeeded(requestedUrl)
        if (securedUrl != requestedUrl) {
            authorizeNavigation(view, securedUrl, loadWhenAllowed = true)
            return true
        }
        return !authorizeNavigation(view, securedUrl, loadWhenAllowed = false)
    }

    /** 地址栏和首次外部导航必须调用此入口，不能直接调用 WebView.loadUrl。 */
    fun navigate(view: WebView, url: String): Boolean =
        authorizeNavigation(view, url, loadWhenAllowed = true)

    private fun authorizeNavigation(view: WebView, rawUrl: String, loadWhenAllowed: Boolean): Boolean {
        val url = upgradeToHttpsIfNeeded(rawUrl)
        val decision = broker.evaluateNavigation(sessionId, tabId, documentGeneration, url, "navigation")
        val allowed = decision is Decision.Allow && broker.consumeNavigation(
            action = decision.action,
            sessionId = sessionId,
            tabId = tabId,
            currentGeneration = documentGeneration,
            rawUrl = url,
            scope = "navigation",
        )
        if (allowed && loadWhenAllowed) view.loadUrl(url)
        return allowed
    }

    private fun upgradeToHttpsIfNeeded(url: String): String {
        val uri = android.net.Uri.parse(url)
        val scheme = uri.scheme.orEmpty().lowercase()
        val host = uri.host.orEmpty().lowercase()
        if (scheme == "http" && host !in allowedHttpDomains) {
            val upgraded = url.replaceFirst("http://", "https://")
            android.util.Log.i("Aegis", "HTTPS-only: 升级 $url → $upgraded")
            return upgraded
        }
        return url
    }

    /** 用户手动放行 HTTP 域名（会话内有效）。 */
    fun allowHttpDomain(domain: String) {
        allowedHttpDomains.add(domain)
    }

    override fun onRenderProcessGone(view: WebView, detail: android.webkit.RenderProcessGoneDetail): Boolean {
        documentGeneration += 1
        broker.updateDocumentGeneration(sessionId, tabId, documentGeneration)
        onRendererGone(view)
        return true
    }

    override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
        documentGeneration += 1
        if (!broker.updateDocumentGeneration(sessionId, tabId, documentGeneration)) {
            android.util.Log.e("Aegis", "未注册或陈旧会话尝试加载页面；已停止加载")
            view.stopLoading()
        }
        super.onPageStarted(view, url, favicon)
    }

    /** 标签关闭时显式释放 Broker 会话，禁止遗留 WebView 再消费旧授权。 */
    fun close() {
        broker.destroySession(sessionId)
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

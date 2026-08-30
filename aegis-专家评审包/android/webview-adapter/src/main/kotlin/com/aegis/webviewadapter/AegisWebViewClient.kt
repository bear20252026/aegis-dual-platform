package com.aegis.webviewadapter

import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
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
    private val requireNavigationConfirmation: Boolean = false,
    private val onNavigationConfirmationRequested: (ApprovalRequest) -> Unit = {},
    private val onNavigationConfirmationResolved: () -> Unit = {},
) : WebViewClient() {

    /** 用户手动放行的 HTTP 域名（会话内有效——照搬 voidbrowser https_only）。 */
    private val allowedHttpDomains = mutableSetOf<String>()
    private var documentGeneration = 0L
    private var pendingConfirmation: PendingNavigationConfirmation? = null

    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val requestedUrl = request.url.toString()
        val securedUrl = upgradeToHttpsIfNeeded(requestedUrl)
        if (securedUrl != requestedUrl) {
            authorizeNavigation(
                view,
                securedUrl,
                loadWhenAllowed = true,
                mayRequireConfirmation = request.isForMainFrame,
            )
            return true
        }
        return !authorizeNavigation(
            view,
            securedUrl,
            loadWhenAllowed = false,
            mayRequireConfirmation = request.isForMainFrame,
        )
    }

    /** 地址栏和首次外部导航必须调用此入口，不能直接调用 WebView.loadUrl。 */
    fun navigate(view: WebView, url: String): Boolean =
        authorizeNavigation(view, url, loadWhenAllowed = true, mayRequireConfirmation = true)

    /**
     * 仅由受信 Compose chrome 的明确批准按钮调用。客户端不会创建授权；它把 Rust
     * 核心登记的 request 原样提交给 Broker，消费成功后才恢复该次导航。
     */
    fun approvePendingNavigation(view: WebView): Boolean {
        val pending = pendingConfirmation ?: return false
        pendingConfirmation = null
        val decision = broker.approveNavigationConfirmation(pending.request, pending.url, pending.scope)
        val action = (decision as? Decision.Allow)?.action ?: run {
            onNavigationConfirmationResolved()
            return false
        }
        val consumed = broker.consumeNavigation(
            action = action,
            sessionId = sessionId,
            tabId = tabId,
            currentGeneration = documentGeneration,
            rawUrl = pending.url,
            scope = pending.scope,
        )
        onNavigationConfirmationResolved()
        if (consumed) view.loadUrl(pending.url)
        return consumed
    }

    /** 由拒绝按钮、对话框关闭、新请求、标签关闭或渲染器失效调用；不恢复导航。 */
    fun rejectPendingNavigation(): Boolean {
        val pending = pendingConfirmation ?: return false
        pendingConfirmation = null
        val rejected = broker.rejectNavigationConfirmation(pending.request)
        onNavigationConfirmationResolved()
        return rejected
    }

    private fun authorizeNavigation(
        view: WebView,
        rawUrl: String,
        loadWhenAllowed: Boolean,
        mayRequireConfirmation: Boolean,
    ): Boolean {
        val url = upgradeToHttpsIfNeeded(rawUrl)
        if (requireNavigationConfirmation && mayRequireConfirmation && pendingConfirmation != null) {
            // 不能自动替换或自动批准旧请求；新的顶层导航先使旧 nonce 失效。
            rejectPendingNavigation()
            return false
        }
        // 统一走策略询问：require_confirmation 是策略级决策（与 BuildConfig
        // 无关）。确认开关只决定「弹面板」还是「自动批准」——此前直接判
        // decision is Allow 导致关闭开关后 RequireConfirmation 全被
        // fail-closed 拒绝（搜索修复上线后再次失效的根因）。
        when (val decision = broker.requestNavigationConfirmation(
            sessionId, tabId, documentGeneration, url, "navigation",
        )) {
            is Decision.RequireConfirmation -> {
                if (requireNavigationConfirmation && mayRequireConfirmation) {
                    pendingConfirmation = PendingNavigationConfirmation(url, "navigation", decision.request)
                    onNavigationConfirmationRequested(decision.request)
                    return false
                }
                // 自动批准：保留 Rust 核心 nonce 语义（等同用户批准后兑换）
                val approved = broker.approveNavigationConfirmation(decision.request, url, "navigation")
                val consumed = approved is Decision.Allow && broker.consumeNavigation(
                    action = approved.action,
                    sessionId = sessionId,
                    tabId = tabId,
                    currentGeneration = documentGeneration,
                    rawUrl = url,
                    scope = "navigation",
                )
                if (consumed && loadWhenAllowed) view.loadUrl(url)
                return consumed
            }

            is Decision.Allow -> {
                val consumed = broker.consumeNavigation(
                    decision.action, sessionId, tabId, documentGeneration, url, "navigation",
                )
                if (consumed && loadWhenAllowed) view.loadUrl(url)
                return consumed
            }

            is Decision.Deny -> return false
        }
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
        rejectPendingNavigation()
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
        rejectPendingNavigation()
        broker.destroySession(sessionId)
    }

    private data class PendingNavigationConfirmation(
        val url: String,
        val scope: String,
        val request: ApprovalRequest,
    )

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

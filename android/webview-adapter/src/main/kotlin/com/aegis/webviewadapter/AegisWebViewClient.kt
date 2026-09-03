package com.aegis.webviewadapter

import android.net.http.SslError
import android.webkit.SafeBrowsingResponse
import android.webkit.SslErrorHandler
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
import com.aegis.broker.Decision

/**
 * 阶段 D（蓝图 android/webview-adapter）：WebViewClient 封装——只把 WebView 回调
 * 转换为请求（不拥有安全策略——ADR-002）。导航/新窗口经 broker 决策（真实拒绝）；
 * onRenderProcessGone 返回 true + 清理 WebView（官方 Termination Handling API——
 * 不返回 true 则系统 kill Activity——调研交叉确认）。
 *
 * P2-1 修复（全面审计 2026-09-04）：补齐 SSL/加载错误回调——原实现无任何
 * 错误处理，证书错误/DNS 失败/HTTP 5xx 一律静默白屏；错误经 [onPageError]
 * 上抛 UI 错误面板（SSL 一律 cancel 绝不 proceed，透明不降级）。
 *
 * 构造参数全部为安全链路显式依赖（回调缺省安全——no-op）。
 */
@Suppress("LongParameterList")
class AegisWebViewClient(
    private val broker: AndroidBroker,
    private val sessionId: String,
    private val tabId: String,
    private val onRendererGone: (WebView) -> Unit,
    private val requireNavigationConfirmation: Boolean = false,
    private val onNavigationConfirmationRequested: (ApprovalRequest) -> Unit = {},
    private val onNavigationConfirmationResolved: () -> Unit = {},
    private val onNavigationDenied: (code: String, detail: String) -> Unit = { _, _ -> },
    private val onPageUrlObserved: (String) -> Unit = {},
    private val onPageError: (description: String, isSsl: Boolean, url: String) -> Unit = { _, _, _ -> },
) : WebViewClient() {
    private var documentGeneration = 0L
    private var pendingConfirmation: PendingConfirmedNavigation? = null

    private companion object {
        /** P2-1 修复：HTTP 错误状态码阈值（>= 该值视为服务器端错误）。 */
        const val HTTP_ERROR_MIN = 400
    }

    override fun shouldOverrideUrlLoading(
        view: WebView,
        request: WebResourceRequest,
    ): Boolean {
        val requestedUrl = request.url.toString()
        // http 请求必须由客户端经 authorizeNavigation 升级加载（loadWhenAllowed=true，
        // 阻断 WebView 原始 http load）；升级本身在 authorizeNavigation 内单次执行。
        val isHttp =
            android
                .net.Uri
                .parse(requestedUrl)
                .scheme
                .orEmpty()
                .lowercase() == "http"
        // P1-2 修复（全面审计批次4）：仅**主框架** http 才走「阻断+升级+
        // loadUrl 升级版」。子框架（iframe）http 此前同样 loadWhenAllowed=true
        // ——authorizeNavigation 决策通过后 view.loadUrl 把 iframe 的 URL
        // 加载进整个 Activity 顶层（页面内任一 http iframe 即可顶替主文档，
        // 导航劫持面）。子框架改落通用分支：broker 决策（Deny → return true
        // 阻断留痕；Allow → return false 放行原始加载——明文由
        // network_security_config 的 cleartext 禁用兜底，iframe 加载失败
        // 但绝不劫持顶层、绝不放行明文）。
        if (isHttp && request.isForMainFrame) {
            authorizeNavigation(
                view,
                requestedUrl,
                loadWhenAllowed = true,
                mayRequireConfirmation = true,
            )
            return true
        }
        return !authorizeNavigation(
            view,
            requestedUrl,
            loadWhenAllowed = false,
            mayRequireConfirmation = request.isForMainFrame,
        )
    }

    /** 地址栏和首次外部导航必须调用此入口，不能直接调用 WebView.loadUrl。 */
    fun navigate(
        view: WebView,
        url: String,
    ): Boolean = authorizeNavigation(view, url, loadWhenAllowed = true, mayRequireConfirmation = true)

    /**
     * 仅由受信 Compose chrome 的明确批准按钮调用。客户端不会创建授权；它把 Rust
     * 核心登记的 request 原样提交给 Broker，消费成功后才恢复该次导航。
     */
    fun approvePendingNavigation(view: WebView): Boolean {
        val pending = pendingConfirmation ?: return false
        pendingConfirmation = null
        val decision = broker.approveNavigationConfirmation(pending.request, pending.url, pending.scope)
        val action =
            (decision as? Decision.Allow)?.action ?: run {
                onNavigationConfirmationResolved()
                return false
            }
        val consumed =
            broker.consumeNavigation(
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
            // P1-4 修复（全量复审 2026-09-01）：不能自动批准旧请求；新顶层导航
            // 先撤销旧 nonce，再对新 URL 重新走确认流程（旧实现直接 return false
            // ——确认框打开期间新导航被静默吞掉，既不弹窗也不提示）。
            rejectPendingNavigation()
        }
        // 统一走策略询问：require_confirmation 是策略级决策（与 BuildConfig
        // 无关）。确认开关只决定「弹面板」还是「自动批准」——此前直接判
        // decision is Allow 导致关闭开关后 RequireConfirmation 全被
        // fail-closed 拒绝（搜索修复上线后再次失效的根因）。
        //
        // P0 修复（全量复审 2026-09-01）：决策前滑动续期会话——此前原生核心
        // 会话 TTL=120s 且无续期，应用启动 2 分钟后所有导航被 session_expired
        // 拒绝（真机复现：连搜索词都被弹「安全提示」）。待审批确认期间不续期，
        // 避免覆盖式重注册孤儿化 pending nonce。
        renewSessionBeforeDecision()
        when (
            val decision =
                broker.requestNavigationConfirmation(
                    sessionId,
                    tabId,
                    documentGeneration,
                    url,
                    "navigation",
                )
        ) {
            is Decision.RequireConfirmation -> {
                if (requireNavigationConfirmation && mayRequireConfirmation) {
                    pendingConfirmation = PendingConfirmedNavigation(url, "navigation", decision.request)
                    onNavigationConfirmationRequested(decision.request)
                    return false
                }
                // 自动批准：保留 Rust 核心 nonce 语义（等同用户批准后兑换）
                val approved = broker.approveNavigationConfirmation(decision.request, url, "navigation")
                val consumed =
                    approved is Decision.Allow &&
                        broker.consumeNavigation(
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
                val consumed =
                    broker.consumeNavigation(
                        decision.action,
                        sessionId,
                        tabId,
                        documentGeneration,
                        url,
                        "navigation",
                    )
                if (consumed && loadWhenAllowed) view.loadUrl(url)
                return consumed
            }

            is Decision.Deny -> {
                return denied(decision.reason, mayRequireConfirmation, url)
            }
        }
    }

    /** P0 修复（全量复审 2026-09-01）：决策前滑动续期会话（待审批确认期间不续期）。 */
    private fun renewSessionBeforeDecision() {
        if (pendingConfirmation == null) {
            broker.renewSession(sessionId, tabId)
        }
    }

    /**
     * P0 修复（全量复审 2026-09-01）：拒绝不再静默——顶层导航拒绝上抛 UI 提示
     * （此前用户只看到白屏/无反应）；子框架拒绝留日志。
     */
    private fun denied(
        reason: com.aegis.broker.DenyReason,
        topLevel: Boolean,
        url: String,
    ): Boolean {
        android.util.Log.w("AegisWebView", "导航被拒: code=${reason.code} detail=${reason.detail} url=$url")
        if (topLevel) onNavigationDenied(reason.code, reason.detail)
        return false
    }

    private fun upgradeToHttpsIfNeeded(url: String): String {
        val uri = android.net.Uri.parse(url)
        val scheme = uri.scheme.orEmpty().lowercase()
        if (scheme == "http") {
            // T3 修复（全面审计批次2 2026-09-04）：原 replaceFirst("http://")
            // 大小写敏感——`HTTP://EXAMPLE.com` 原样放行明文（scheme 判定处
            // 已 lowercase 但升级未同步）。改忽略大小写替换前缀。
            val upgraded = url.replaceFirst(Regex("^http://", RegexOption.IGNORE_CASE), "https://")
            android.util.Log.i("Aegis", "HTTPS-only: 升级 $url → $upgraded")
            return upgraded
        }
        return url
    }

    override fun onRenderProcessGone(
        view: WebView,
        detail: android.webkit.RenderProcessGoneDetail,
    ): Boolean {
        rejectPendingNavigation()
        documentGeneration += 1
        broker.updateDocumentGeneration(sessionId, tabId, documentGeneration)
        onRendererGone(view)
        return true
    }

    override fun onPageStarted(
        view: WebView,
        url: String?,
        favicon: android.graphics.Bitmap?,
    ) {
        documentGeneration += 1
        if (!broker.updateDocumentGeneration(sessionId, tabId, documentGeneration)) {
            android.util.Log.e("Aegis", "未注册或陈旧会话尝试加载页面；已停止加载")
            view.stopLoading()
        }
        // P1-6 修复（全量复审 2026-09-01）：真实页面 URL 上抛——地址栏随实际
        // 页面同步（此前重定向/页内跳转后地址栏永远显示陈旧 URL）。
        if (!url.isNullOrBlank()) onPageUrlObserved(url)
        super.onPageStarted(view, url, favicon)
    }

    /**
     * P2-1 修复（全面审计 2026-09-04）：SSL 证书错误——保持默认行为 cancel
     * （绝不调用 handler.proceed()：跳过证书校验等于向中间人攻击放行），
     * 并上报 UI 错误面板（原默认 cancel 后静默白屏，用户无从得知被拦截原因）。
     */
    override fun onReceivedSslError(
        view: WebView,
        handler: SslErrorHandler,
        error: SslError,
    ) {
        handler.cancel()
        val url = error.url
        android.util.Log.w(
            "AegisWebView",
            "SSL 证书校验失败已取消: url=$url primaryError=${error.primaryError}",
        )
        onPageError("证书校验失败（${sslPrimaryErrorName(error.primaryError)}）", true, url)
    }

    /**
     * P2-1 修复（全面审计 2026-09-04）：主框架加载失败上报（DNS 失败/断网/
     * 不支持 scheme 等——原实现静默白屏）；子框架错误不上报（不阻塞整页展示）。
     */
    override fun onReceivedError(
        view: WebView,
        request: WebResourceRequest,
        error: WebResourceError,
    ) {
        super.onReceivedError(view, request, error)
        if (!request.isForMainFrame) return
        val description = error.description?.toString().orEmpty()
        android.util.Log.w(
            "AegisWebView",
            "主框架加载错误: code=${error.errorCode} desc=$description url=${request.url}",
        )
        val text = mainFrameErrorText(error.errorCode, description)
        onPageError(text, false, request.url.toString())
    }

    /**
     * P2-1 修复（全面审计 2026-09-04）：主框架 HTTP >= 400 上报。该回调对
     * 任意资源都会触发——子框架/子资源的 4xx/5xx 不应遮蔽整页内容，仅
     * `request.isForMainFrame` 时上报。
     */
    override fun onReceivedHttpError(
        view: WebView,
        request: WebResourceRequest,
        errorResponse: WebResourceResponse,
    ) {
        super.onReceivedHttpError(view, request, errorResponse)
        if (!request.isForMainFrame) return
        if (errorResponse.statusCode < HTTP_ERROR_MIN) return
        android.util.Log.w(
            "AegisWebView",
            "主框架 HTTP 错误: status=${errorResponse.statusCode} url=${request.url}",
        )
        onPageError("服务器返回错误（HTTP ${errorResponse.statusCode}）", false, request.url.toString())
    }

    /** P2-1 修复：SslError.primaryError → 简短中文说明（错误面板文案）。 */
    private fun sslPrimaryErrorName(primaryError: Int): String =
        when (primaryError) {
            SslError.SSL_DATE_INVALID -> "证书日期无效"
            SslError.SSL_EXPIRED -> "证书已过期"
            SslError.SSL_IDMISMATCH -> "证书域名不匹配"
            SslError.SSL_NOTYETVALID -> "证书尚未生效"
            SslError.SSL_UNTRUSTED -> "证书颁发机构不受信任"
            SslError.SSL_INVALID -> "证书无效"
            else -> "未知证书错误"
        }

    /** P2-1 修复：主框架错误码/描述 → 中文文案（未识别错误码回退原始描述）。 */
    private fun mainFrameErrorText(
        errorCode: Int,
        description: String,
    ): String {
        val reason =
            when (errorCode) {
                // ERROR_* 常量定义在 WebViewClient（非 WebResourceError）
                WebViewClient.ERROR_HOST_LOOKUP -> "找不到服务器"

                WebViewClient.ERROR_CONNECT -> "无法连接服务器"

                WebViewClient.ERROR_TIMEOUT -> "连接超时"

                WebViewClient.ERROR_UNSUPPORTED_SCHEME -> "不支持的地址类型"

                else -> description.ifBlank { "加载失败" }
            }
        return "页面加载失败：$reason"
    }

    /** 标签关闭时显式释放 Broker 会话，禁止遗留 WebView 再消费旧授权。 */
    fun close() {
        rejectPendingNavigation()
        broker.destroySession(sessionId)
    }

    private data class PendingConfirmedNavigation(
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

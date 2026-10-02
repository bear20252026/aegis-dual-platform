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
    // AD-284（2026-10-01 审计）：mailto:/tel:/sms: 等外跳 scheme 的主框架
    // 导航——显式上抛（app 层 Toast「不支持该类链接」），不再与恶意
    // scheme 同走静默 Deny。回调参数：scheme、原始 URL。
    private val onUnsupportedSchemeNavigation: (scheme: String, url: String) -> Unit = { _, _ -> },
    private val onPageUrlObserved: (String) -> Unit = {},
    // AD-035（2026-09-24 审计）：库模块不持 UI 文案——错误以（错误码, 机器可读
    // detail, isSsl, url）结构上抛，中文文案映射收敛在 app 层（BrowserViewModel）。
    private val onPageError: (code: String, detail: String, isSsl: Boolean, url: String) -> Unit =
        { _, _, _, _ -> },
    // AD-050（2026-09-24 审计）：自动批准分支的决策源可注入——生产默认委托
    // broker.approveNavigationConfirmation；单测注入假 Decision 后
    // RequireConfirmation+自动批准路径可离线断言（此前 broker 硬编码不可替）。
    private val autoApproveDecision: (request: ApprovalRequest, rawUrl: String, scope: String) -> Decision =
        { request, rawUrl, scope -> broker.approveNavigationConfirmation(request, rawUrl, scope) },
) : WebViewClient() {
    private var documentGeneration = 0L
    private var pendingConfirmation: PendingConfirmedNavigation? = null

    companion object {
        /** AD-330（2026-10-02 审计）：本类日志 tag 单源（原 "AegisWebView"/"Aegis" 混用）。 */
        private const val TAG = "AegisWebView"

        /**
         * AD-284：外跳 scheme 集——系统/第三方应用处理的链接形态（WebView 自身
         * 无法加载）。这些 schemes 的主框架导航阻断后必须给用户显式反馈，否则
         * 表现为「点了没反应」的静默死链。
         *
         * AD-304（2026-10-02 审计）：补 smsto/mmsto/geo——短信/地理位置链接与
         * mailto/tel/sms 同为系统分发形态，此前落策略拒绝（恐吓提示）而非
         * 「不支持该类链接」分型反馈。AD-303 配套：companion 化供 app 层
         * （BrowserViewModel 地址栏输入分型）共用同一集合，消除双源漂移面。
         */

        // public：app 模块（BrowserViewModel 地址栏分型——AD-303）跨模块共用同源集合
        // （ktlint：注释紧随 KDoc 须空行分隔——云端首跑实证）
        val externalHandlerSchemes = setOf("mailto", "tel", "sms", "smsto", "mmsto", "geo")
    }

    override fun shouldOverrideUrlLoading(
        view: WebView,
        request: WebResourceRequest,
    ): Boolean {
        val requestedUrl = request.url.toString()
        // AD-255（2026-10-01 审计）：以 request.isForMainFrame 为主分支条件——
        // 原实现 `isHttp && isForMainFrame` 把 https 主框架链接漏进子框架轻量
        // 分支（RequireConfirmation 确认对话框永不出现、Deny 不上抛——静默
        // 死链）。scheme 现在只决定是否升级与外跳反馈，不再影响主/子分派：
        // 主框架一律走 authorizeNavigation 全链（确认登记/自动批准 + Deny 以
        // topLevel=true 上抛），子框架保持轻量判定（AD-246）。
        val scheme = schemePrefixOf(requestedUrl)
        if (request.isForMainFrame) {
            return handleMainFrameNavigation(view, requestedUrl, scheme)
        }
        return handleSubFrameNavigation(view, requestedUrl)
    }

    /**
     * AD-255：主框架导航——外跳 scheme（mailto:/tel:/sms:）显式反馈；其余
     * （http/https/其他）走 authorizeNavigation 全链（阻断 WebView 原始
     * 加载，放行时由客户端经 broker 升级后 loadUrl——P1-2 修复语义不变）。
     */
    private fun handleMainFrameNavigation(
        view: WebView,
        requestedUrl: String,
        scheme: String,
    ): Boolean {
        // AD-284：外跳 scheme——显式上抛不支持提示，阻断 WebView 原始加载。
        // 与策略拒绝（onNavigationDenied）分型，避免「点邮件链接无反应」的
        // 静默死链。
        if (scheme in externalHandlerSchemes) {
            android.util.Log.w(TAG, "主框架外跳 scheme 阻断: scheme=$scheme ${LogRedact.redact(requestedUrl)}")
            onUnsupportedSchemeNavigation(scheme, requestedUrl)
            return true
        }
        // AD-320（2026-10-02 审计）：loadWhenAllowed 参数删除——两个调用点
        // 恒传 true，参数只制造「存在不加载分支」的假状态空间。
        authorizeNavigation(
            view,
            requestedUrl,
            mayRequireConfirmation = true,
        )
        return true
    }

    /**
     * AD-246（2026-09-26 审计）：子框架轻量判定——单次 evaluateNavigation。
     * 此前子框架与主框架同走「确认登记+自动批准+consumeNavigation」全链
     * （native 模式下每次子框架导航三次 JNI→Rust 持锁跨界调用，iframe
     * 密集页开销显著）。Deny → 阻断留痕；Allow → 放行原始加载（不消费
     * 顶层授权对象）；RequireConfirmation 无子框架确认 UI 面——fail-closed
     * 阻断。
     * AD-178（审计 2026-09-23 清单·A7 批）：会话续期仅主框架——本路径有意
     * 不调 renewSessionBeforeDecision：①iframe 密集页逐导航续期会把「滑动
     * TTL」放大成常态性 JNI 重注册；②子框架导航不表达「用户仍在活跃浏览」
     * 的顶层语义（无主框架事件的页面不该被子框架保活）。
     *
     * AD-309（2026-10-02 审计）：Allow 放行与主框架同口径——原实现升级
     * 只用于策略判定、放行仍载原始 http（明文子框架请求照发，cleartext
     * 全局禁用下表现为子框架静默加载失败）。现 Allow 时返回 true 阻断
     * 原始加载并由 view.loadUrl(升级后 URL) 重发（Deny/确认阻断语义不变）。
     */
    private fun handleSubFrameNavigation(
        view: WebView,
        requestedUrl: String,
    ): Boolean {
        val subFrameUrl = upgradeToHttpsIfNeeded(requestedUrl)
        // ktlint multiline-expression：subject 提取为独立语句——嵌套 when (val x = ...)
        // 触发「多行表达式应另起一行」（云端首跑实证 :141）
        val decision =
            broker.evaluateNavigation(sessionId, tabId, documentGeneration, subFrameUrl, "navigation")
        val blocked = when (decision) {
            is Decision.Allow -> {
                // AD-309：经升级后 URL 重发（不消费顶层授权对象——子框架
                // 轻量路径不产生新授权，重发请求自身仍受本回调约束）
                view.loadUrl(subFrameUrl)
                true
            }

            is Decision.RequireConfirmation -> {
                android.util.Log.w(
                    TAG,
                    "子框架确认型导航被阻断（无子框架确认 UI 面）: ${LogRedact.redact(subFrameUrl)}",
                )
                true
            }

            is Decision.Deny -> {
                denied(decision.reason, topLevel = false, url = subFrameUrl)
                true
            }
        }
        return blocked
    }

    /** 地址栏和首次外部导航必须调用此入口，不能直接调用 WebView.loadUrl。 */
    fun navigate(
        view: WebView,
        url: String,
    ): Boolean = authorizeNavigation(view, url, mayRequireConfirmation = true)

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
                // AD-050：决策经注入源（生产=broker 委托；测试=替身）。
                val approved = autoApproveDecision(decision.request, url, "navigation")
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
                if (consumed) view.loadUrl(url)
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
                if (consumed) view.loadUrl(url)
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
        // AD-211（2026-09-26 审计）：日志行经 denialLogLine 单源组装——detail
        // 内嵌的明文 URL/query 一并脱敏（此前 detail 直拼原文入 logcat）。
        android.util.Log.w(TAG, WebViewErrorCodes.denialLogLine(reason, url))
        if (topLevel) onNavigationDenied(reason.code, reason.detail)
        return false
    }

    /**
     * scheme 前缀识别（纯字符串——AD-010/011 JVM 可测化）。
     * RFC 3986 scheme 字符集（字母数字 + + - .）之外的输入返回空串——
     * 与 Uri.parse 对无 scheme/相对 URL 返回 null scheme 的判定语义一致。
     */
    internal fun schemePrefixOf(url: String): String =
        url
            .substringBefore(':', missingDelimiterValue = "")
            .lowercase()
            .takeIf { it.isNotEmpty() && it.all { c -> c.isLetterOrDigit() || c == '+' || c == '-' || c == '.' } }
            .orEmpty()

    private fun upgradeToHttpsIfNeeded(url: String): String {
        if (schemePrefixOf(url) == "http") {
            // T3 修复（全面审计批次2 2026-09-04）：原 replaceFirst("http://")
            // 大小写敏感——`HTTP://EXAMPLE.com` 原样放行明文（scheme 判定处
            // 已 lowercase 但升级未同步）。改忽略大小写替换前缀。
            val upgraded = url.replaceFirst(Regex("^http://", RegexOption.IGNORE_CASE), "https://")
            // AD-233（2026-09-26 审计）：升级日志对每条 http 资源（含全部子
            // 框架）各打一条——降为 isLoggable(DEBUG) 门控（开发期 setprop
            // 可开启，release 默认静默）。
            if (android.util.Log.isLoggable(TAG, android.util.Log.DEBUG)) {
                android.util.Log.d(TAG, "HTTPS-only: 升级 ${LogRedact.redact(url)} → ${LogRedact.redact(upgraded)}")
            }
            return upgraded
        }
        return url
    }

    override fun onRenderProcessGone(
        view: WebView,
        detail: android.webkit.RenderProcessGoneDetail,
    ): Boolean {
        rejectPendingNavigation()
        // AD-201（审计 2026-09-23 清单·A7 批）：代际推进失败回滚自增——
        // 原实现本地自增先行、核心同步失败不回滚，本地代际与核心永久分叉
        // （此后每次推进都差一步、全部被单步门禁拒绝）。失败即回滚，
        // 保持「本地代际 == 核心已确认代际」不变式（重试可从原值再推进）。
        documentGeneration += 1
        if (!broker.updateDocumentGeneration(sessionId, tabId, documentGeneration)) {
            documentGeneration -= 1
            android.util.Log.e(TAG, "渲染进程崩溃后代际推进被拒（会话未注册/陈旧）")
        }
        onRendererGone(view)
        return true
    }

    override fun onPageStarted(
        view: WebView,
        url: String?,
        favicon: android.graphics.Bitmap?,
    ) {
        // AD-201：同 onRenderProcessGone——同步失败回滚本地自增，消除分叉。
        documentGeneration += 1
        if (!broker.updateDocumentGeneration(sessionId, tabId, documentGeneration)) {
            documentGeneration -= 1
            android.util.Log.e(TAG, "未注册或陈旧会话尝试加载页面；已停止加载")
            view.stopLoading()
            // AD-265（2026-10-01 审计）：代际推进失败已 stopLoading——阻断的
            // URL 不得再上抛地址栏（原实现仍观察 URL，地址栏被阻断 URL 覆盖，
            // 页面实际未加载形成状态污染）。推进成功才继续观察/上抛。
            super.onPageStarted(view, url, favicon)
            return
        }
        // AD-256（2026-10-01 审计）：30x 重定向/表单 POST/reload 不经过
        // shouldOverrideUrlLoading——此前放行后的 302 跳 userinfo 形态/
        // 确认策略 URL 整链绕过。onPageStarted 对主框架 URL（本回调只对
        // 主框架触发）做轻量 evaluateNavigation 复核：Deny 即 stopLoading +
        // 顶层上抛。RequireConfirmation 有意不阻断——用户批准后 loadUrl 的
        // 导航同样触发本回调，若此处 fail-closed 会破坏确认功能语义；
        // 代际推进先行完成（复核用推进后的代际，不破坏 AD-201 回滚逻辑）。
        if (!url.isNullOrBlank() && schemePrefixOf(url).let { it == "http" || it == "https" }) {
            val target = upgradeToHttpsIfNeeded(url)
            val recheck = broker.evaluateNavigation(sessionId, tabId, documentGeneration, target, "navigation")
            if (recheck is Decision.Deny) {
                denied(recheck.reason, topLevel = true, url = target)
                view.stopLoading()
                super.onPageStarted(view, url, favicon)
                return
            }
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
     *
     * AD-271（2026-10-01 审计）：按 error.url 归属判定——与主框架当前 URL
     * （view.url）一致的失败按整页错误上抛；归属不上的（子资源形态，或个别
     * WebView 实现对子资源触发本回调）只 cancel + 留痕，不上抛整页遮罩
     * （子资源证书错不该遮蔽整页内容）。view.url 为空（无已提交主文档）
     * 时保守按主框架处理（保持既有错误面，不静默）。
     */
    override fun onReceivedSslError(
        view: WebView,
        handler: SslErrorHandler,
        error: SslError,
    ) {
        handler.cancel()
        val url = error.url
        val mainFrameUrl = view.url
        val isMainFrameFailure = mainFrameUrl.isNullOrEmpty() || url == mainFrameUrl
        if (isMainFrameFailure) {
            android.util.Log.w(
                TAG,
                "SSL 证书校验失败已取消: url=${LogRedact.redact(url)} primaryError=${error.primaryError}",
            )
            // AD-035：detail = SslError.primaryError 整数值（app 层映射中文文案）
            // AD-136（审计 2026-09-23 清单·A6 批）：错误码字面量 → 常量单源
            onPageError(WebViewErrorCodes.ERROR_SSL_CERTIFICATE, error.primaryError.toString(), true, url)
        } else {
            android.util.Log.w(
                TAG,
                "子资源 SSL 证书校验失败已取消（不遮蔽整页）: url=${LogRedact.redact(url)} primaryError=${error.primaryError}",
            )
        }
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
            TAG,
            "主框架加载错误: code=${error.errorCode} desc=$description url=${LogRedact.redact(request.url.toString())}",
        )
        // AD-035：detail = "errorCode:description"（app 层按 errorCode 映射文案）
        onPageError(
            WebViewErrorCodes.ERROR_MAIN_FRAME,
            "${error.errorCode}:$description",
            false,
            request.url.toString(),
        )
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
        if (errorResponse.statusCode < WebViewErrorCodes.HTTP_ERROR_MIN) return
        android.util.Log.w(
            TAG,
            "主框架 HTTP 错误: status=${errorResponse.statusCode} url=${LogRedact.redact(request.url.toString())}",
        )
        // AD-035：detail = HTTP 状态码字符串（app 层映射文案）；AD-136 常量化
        onPageError(WebViewErrorCodes.ERROR_HTTP, errorResponse.statusCode.toString(), false, request.url.toString())
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
        // AD-291（2026-10-01 审计）：恒 backToSafety 在无历史时无处可退
        // （新标签直开恶意链接 → backToSafety 白屏）。有历史回安全页；
        // 无历史显示 Safe Browsing 插页（API 27+；API 26 设备 showInterstitial
        // 不可用，仍回退 backToSafety）。绝不 proceed——阻断语义不变。
        val interstitialAvailable =
            android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O_MR1
        when {
            view.canGoBack() || !interstitialAvailable -> callback.backToSafety(true)
            else -> callback.showInterstitial(true)
        }
        android.util.Log.w(
            TAG,
            "SafeBrowsing 命中阻断: ${LogRedact.redact(request.url.toString())} threatType=$threatType",
        )
    }
}

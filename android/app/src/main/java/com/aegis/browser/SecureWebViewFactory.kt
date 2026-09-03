package com.aegis.browser

import android.content.Context
import android.webkit.WebView
import com.aegis.broker.ApprovalRequest
import com.aegis.webviewadapter.AegisWebViewClient
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

/**
 * 安全 WebView 工厂（单文件单职责：统一创建带完整安全边界的 WebView）。
 *
 * 改动（单路径收敛——专家审计）：WebView 创建时同时注入 AegisWebViewClient，
 * 确保所有导航回调经 Broker 决策（fail-closed），不再绕过。
 *
 * 职责拆分（重构 2026-09-03）：脚本注入 → WebViewHardening；下载处理 →
 * WebViewDownloadHandler；受控导航器 → SecureNavigator.kt。本文件只保留
 * 创建/注册表/释放生命周期。
 */
object SecureWebViewFactory {
    private val sessionCounter = AtomicLong(0)

    // 导航器注册表（显式生命周期——H-4 修复）。
    // 历史教训一：曾用 View.setTag(generateViewId(), ...) 存导航器——
    // generateViewId() 的 package id 是 0x01（framework 区段），
    // 而 setTag(int,...) 要求 ≥0x02 的应用资源 id → 真机启动必崩。
    // 历史教训二（H-4 审计 2026-08-31）：曾用 WeakHashMap——但值
    // （SecureNavigator）强引用键（WebView），键永不可达、条目永不回收，
    // 每次新建标签泄漏一个 WebView 及其 Chromium 资源。
    // 现改为显式注册表：create() 注册，release() 注销并销毁 Broker 会话。
    private val navigators = ConcurrentHashMap<WebView, SecureNavigator>()

    /**
     * 创建并完成安全配置的 WebView（导航经 Broker 决策 + 指纹防护注入）。
     *
     * LongParameterList 豁免（批次二 P1-3/4/6）：6 个参数全部是导航
     * 回调装配点——与 [AegisWebViewClient] 构造器同口径（回调装配点
     * 参数多属设计使然，拆分反而引入状态对象间接层）。
     */
    @Suppress("LongParameterList")
    fun create(
        context: Context,
        onNavigationConfirmationRequested: (WebView, ApprovalRequest) -> Unit = { _, _ -> },
        onNavigationConfirmationResolved: (WebView) -> Unit = {},
        onNavigationDenied: (WebView, String, String) -> Unit = { _, _, _ -> },
        onPageUrlObserved: (WebView, String) -> Unit = { _, _ -> },
        onTitleObserved: (WebView, String) -> Unit = { _, _ -> },
        onRendererGone: (WebView) -> Unit = {},
        onPageError: (WebView, String, Boolean, String) -> Unit = { _, _, _, _ -> },
    ): WebView {
        // A-6 修复（架构审计 2026-08-31）：Broker 由 Application 持有——
        // 工厂不再静态单例持有（可测试、可隔离、生命周期显式）
        val broker = (context.applicationContext as AegisApplication).broker
        val webView = WebView(context)
        BrowserEngine(webView, onTitleObserved = { onTitleObserved(webView, it) }).configure()
        val sessionId = "session-${sessionCounter.incrementAndGet()}"
        val tabId = "tab-$sessionId"
        if (!broker.registerSession(sessionId, tabId)) {
            // fail-closed 前留根因线索（logcat -s AegisBroker；典型：
            // release minified 混淆 JNA Abi 接口 → native 符号映射失败）
            android.util.Log.e(
                "AegisBroker",
                "registerSession failed: session=$sessionId, " +
                    "REQUIRE_NATIVE_POLICY_CORE=${com.aegis.broker.BuildConfig.REQUIRE_NATIVE_POLICY_CORE}",
            )
            check(false) { "无法注册安全浏览会话（详见 logcat -s AegisBroker）" }
        }
        WebViewHardening.install(webView, WebViewHardening.newSessionSeed())
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = sessionId,
                tabId = tabId,
                onRendererGone = { deadWebView ->
                    // P1-3 修复（全量复审 2026-09-01）：上抛调用方重建（原 no-op
                    // ——渲染进程崩溃后标签永久白屏）
                    onRendererGone(deadWebView)
                },
                requireNavigationConfirmation =
                    com.aegis.broker.BuildConfig.REQUIRE_NAVIGATION_CONFIRMATION,
                onNavigationConfirmationRequested = { request ->
                    onNavigationConfirmationRequested(webView, request)
                },
                onNavigationConfirmationResolved = { onNavigationConfirmationResolved(webView) },
                onNavigationDenied = { code, detail ->
                    onNavigationDenied(webView, code, detail)
                },
                onPageUrlObserved = { url ->
                    onPageUrlObserved(webView, url)
                },
                onPageError = { description, isSsl, url ->
                    // P2-1 修复（全面审计 2026-09-04）：SSL/加载错误上抛调用方
                    // （ViewModel 错误面板——原静默白屏）。
                    onPageError(webView, description, isSsl, url)
                },
            )
        webView.webViewClient = client
        navigators[webView] = SecureNavigator(webView, client)
        // 首页宿主桥（ADR-003 复审口径）：仅暴露入口级无敏感操作
        // （导航走 Broker 授权；壁纸/引擎为偏好写入；画板为内置资源跳转）
        webView.addJavascriptInterface(
            AegisHomeBridge(context.applicationContext) { webView },
            "AegisBridge",
        )
        // H-6 修复（审计 2026-08-31）：下载防线接线——原 DownloadPolicy
        // 为死代码，WebView 默认下载行为未处理（危险扩展确认机制不存在、
        // 下载静默失败）。统一收口：DownloadPolicy 判定 → DownloadManager。
        webView.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            WebViewDownloadHandler.handleDownload(
                webView,
                url.orEmpty(),
                mimeType.orEmpty(),
                contentDisposition.orEmpty(),
            )
        }
        return webView
    }

    /** 仅工厂创建的 WebView 才拥有受控导航器；不存在时调用方必须拒绝外部导航。 */
    fun navigatorFor(webView: WebView): SecureNavigator? = navigators[webView]

    /**
     * H-4 修复（审计 2026-08-31）：标签关闭 / Activity 销毁时的统一释放口。
     * 注销导航器并销毁对应 Broker 会话——未注销的 WebView 不再能消费授权，
     * 注册表条目随标签生命周期精确回收（替代失效的 WeakHashMap 语义）。
     */
    fun release(webView: WebView) {
        navigators.remove(webView)?.close()
    }

    /**
     * WebView 销毁统一序列（单源）：停载 → 摘除页面 → 注销导航器/Broker 会话 → destroy。
     * 标签关闭（TabManager.closeTab）与 Activity 销毁（MainActivity.onDestroy）共用，
     * 此前两处各自手写一半序列（审计 2026-09-02 收敛）。
     */
    fun tearDown(webView: WebView) {
        webView.stopLoading()
        webView.loadUrl("about:blank")
        release(webView)
        webView.destroy()
    }
}

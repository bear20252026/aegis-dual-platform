package com.aegis.browser

import android.content.Context
import android.webkit.WebView
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest

/**
 * AD-103（审计 2026-09-23 清单·A6 批）：WebView 事件装配对象——把
 * SecureWebViewFactory.create 的回调装配与页面事件处理体从 BrowserViewModel
 * 抽出（ViewModel 只保留状态与用户意图入口；本类只做「事件 → 状态写入」
 * 的单向装配）。
 *
 * 与宿主的全部交互经 [Host] 接缝：装配点不持有 StateFlow/lateinit 引用，
 * init 前的回调（activeTabManager = null）安全降级。
 *
 * @param broker                    透传 SecureWebViewFactory.create
 * @param host                      状态写入接缝（BrowserViewModel 实现）
 * @param onRendererGone            渲染进程崩溃上抛（重建需 viewModelScope，
 *                                  留在 ViewModel）
 * @param onConfirmationRequested   待审批登记上抛（ViewModel 单写点）
 * @param onConfirmationResolved    待审批解除上抛
 */
internal class WebViewEventAssembly(
    private val broker: AndroidBroker,
    private val host: Host,
    private val onRendererGone: (WebView) -> Unit,
    private val onConfirmationRequested: (WebView, ApprovalRequest) -> Unit,
    private val onConfirmationResolved: (WebView) -> Unit,
) {
    /** 宿主接缝：装配点可触达的状态写入面（只收窄所需操作）。 */
    internal interface Host {
        /** 当前 TabManager（init 前为 null——事件回调安全降级）。 */
        val activeTabManager: TabManager?

        /** 地址栏草稿激活中（页面 URL 不得覆盖用户输入）。 */
        val isAddressDraftActive: Boolean

        /** 首页 file:// 占位映射（AD-063）。 */
        fun displayAddress(url: String): String

        /** 地址栏写入（仅草稿未激活且为当前标签时由装配点调用）。 */
        fun submitPageAddress(url: String)

        /** 清除页面错误（当前标签新页面开始）。 */
        fun clearPageError()

        /** 写入页面错误面板状态。 */
        fun submitPageError(error: PageError)

        /** 安全提示写入。 */
        fun submitWebViewAlert(text: String)

        /** 标签列表/可用性随事件刷新（AD-225 URL 回调尾部刷新同口径）。 */
        fun refreshTabs()

        /** 错误文案资源解析（appContext.getString 函数化）。 */
        fun errorStrings(): PageErrorTexts.Strings
    }

    /** 创建装配完成的 WebView（BrowserViewModel.createSecureWebView 的实现体）。 */
    fun create(context: Context): WebView =
        SecureWebViewFactory.create(
            broker = broker,
            context = context,
            onNavigationConfirmationRequested = onConfirmationRequested,
            onNavigationConfirmationResolved = onConfirmationResolved,
            onNavigationDenied = { _, code, _ ->
                // P0 修复（全量复审 2026-09-01）：顶层导航被拒不再静默——经
                // webViewAlert 上抛 UI（此前用户只看到白屏/无反应）。
                host.submitWebViewAlert(
                    when (code) {
                        SESSION_EXPIRED_CODE -> host.errorStrings().text(R.string.session_expired)
                        else -> host.errorStrings().text(R.string.nav_rejected_code, code)
                    },
                )
            },
            onPageUrlObserved = ::onPageUrlObserved,
            onTitleObserved = ::onTitleObserved,
            onRendererGone = onRendererGone,
            onPageError = ::onPageError,
        )

    /**
     * 页面 URL 回调处理体。P1-6 修复（全量复审 2026-09-01）：地址栏随实际
     * 页面同步。P2 修复：用户编辑草稿期间不覆盖输入（提交后恢复正常同步）。
     * P2-1 修复（全面审计 2026-09-04）：onPageStarted → URL 变化即清除错误
     * 面板（重试/新导航开始后旧错误不残留）。
     */
    private fun onPageUrlObserved(
        webView: WebView,
        url: String,
    ) {
        val tm = host.activeTabManager ?: return
        if (tm.current()?.webView === webView) {
            host.clearPageError()
        }
        if (url.isNotBlank()) {
            // AD-036（2026-09-24 审计）：收敛到 TabManager.updateUrl copy 单写点
            // （与 updateTitle 同模式，StateFlow 依赖 equals 感知变化）。
            tm.list().firstOrNull { it.webView === webView }?.let {
                tm.updateUrl(it.id, url)
            }
            if (!host.isAddressDraftActive && tm.current()?.webView === webView) {
                host.submitPageAddress(host.displayAddress(url))
            }
        }
        // AD-225（2026-09-26 审计）：URL 回调尾部刷新（与 onTitleObserved 同口径）。
        host.refreshTabs()
    }

    /**
     * 标题回调处理体。P0 修复（全库审计 2026-09-02）：页面标题回填 Tab.title
     * ——经 TabManager.updateTitle（copy 替换实例）单写点。
     */
    private fun onTitleObserved(
        webView: WebView,
        title: String,
    ) {
        val tm = host.activeTabManager ?: return
        if (title.isBlank()) return
        val target = tm.list().firstOrNull { it.webView === webView }
        // AD-033（2026-09-24 审计）：页面标题是远端可控输入——换行可伪造多行
        // 日志（logcat 注入），截断防日志洪泛（AD-103：净化收敛 LogSanitize 单源）。
        android.util.Log.i(
            "Aegis",
            "R12 titleHit tab=${target?.id} title=${LogSanitize.flatten(title, TITLE_LOG_MAX_LENGTH)}",
        )
        target?.let { tm.updateTitle(it.id, title) }
        host.refreshTabs()
    }

    /**
     * 页面错误回调处理体。P2-1 修复（全面审计 2026-09-04）：仅当前活动标签
     * 的错误上屏。AD-035：错误码结构上抛——文案映射收敛 [PageErrorTexts]。
     */
    private fun onPageError(
        webView: WebView,
        code: String,
        detail: String,
        isSsl: Boolean,
        url: String,
    ) {
        val tm = host.activeTabManager ?: return
        if (tm.current()?.webView !== webView) return
        host.submitPageError(
            PageError(
                description = PageErrorTexts.textFor(code, detail, host.errorStrings()),
                isSsl = isSsl,
                url = url,
                // AD-215：绑定归属标签的 WebView 引用（切换/关闭时对账清除）
                webView = webView,
            ),
        )
    }

    private companion object {
        /** broker deny code：原生会话过期（导航拒绝提示的分型文案）。 */
        const val SESSION_EXPIRED_CODE = "session_expired"

        /** AD-033：日志用标题截断上限（防日志洪泛）。 */
        const val TITLE_LOG_MAX_LENGTH = 120
    }
}

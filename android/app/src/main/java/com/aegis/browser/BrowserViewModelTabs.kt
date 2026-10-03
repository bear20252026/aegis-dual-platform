package com.aegis.browser

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 拆分批（2026-10-03 剩余项批·第二块）：BrowserViewModel 的「标签生命周期 +
 * 渲染崩溃重建」内聚块单文件——原内嵌于 BrowserViewModel（回归改造红线
 * 500 行的登记欠账）。以显式 lambda 接缝持有宿主能力（AD-103/
 * BrowserViewModelConfirmations 同款模式）：保持 BrowserViewModel 公开委托
 * 签名不变（detekt 基线签名/JVM 单测零改动），接缝成员不外泄公开 API。
 *
 * 状态归属不变式（与原实现逐行等价）：
 * - [tabs]/[activeIndex] 经 [refresh] 从 TabManager 同步（AD-064 口径：
 *   前进/后退可用性随刷新点同步）；
 * - 地址栏展示：草稿激活时 [refresh] 不覆盖（P2 修复——多标签草稿互踩）；
 * - 待审批/待确认下载在 [newTab]/[switchTo]/[closeTab] 的撤销语义
 *   （AD-215/AD-224/AD-331——确认与下载单槽不得跨标签/跨销毁存续）。
 *
 * LongParameterList 豁免（BrowserViewModelHost 同款先例）：10 个参数全部
 * 是标签块的状态缝/宿主缝装配点——拆分反而引入状态对象间接层。
 */
@Suppress("LongParameterList")
internal class BrowserViewModelTabs(
    /** 标签 WebView 创建缝（webViewEvents.create——装配点单源）。 */
    private val createWebView: (android.content.Context) -> WebView,
    /** P0-6：崩溃重建 context 解析缝（宿主 Activity 优先，回退 appContext）。 */
    private val rebuildContext: () -> android.content.Context?,
    /** AD-059：裸 Handler → viewModelScope(Main)——生命周期感知由 VM 侧承担。 */
    private val launchOnMain: (() -> Unit) -> Unit,
    /** 地址栏草稿标记缝（refresh 只读；切换/新建/关闭路径清除）。 */
    private val isDraftActive: () -> Boolean,
    private val clearDraft: () -> Unit,
    /** 地址栏展示写缝（refresh 草稿未激活时同步当前标签 URL）。 */
    private val setAddress: (String) -> Unit,
    /** AD-215：页面错误单槽缝（归属对账——错误不得遮罩切换后的标签）。 */
    private val pageErrorWebView: () -> WebView?,
    private val clearPageError: () -> Unit,
    /** 确认/下载单槽控制器（newTab/switchTo/closeTab 的撤销语义落点）。 */
    private val confirmations: BrowserViewModelConfirmations,
) {
    private var tabManager: TabManager? = null

    fun tabManagerOrNull(): TabManager? = tabManager

    private val _tabs = MutableStateFlow<List<Tab>>(emptyList<Tab>())
    val tabs: StateFlow<List<Tab>> = _tabs.asStateFlow()

    private val _activeIndex = MutableStateFlow(0)
    val activeIndex: StateFlow<Int> = _activeIndex.asStateFlow()

    /** AD-064（2026-09-24 审计）：前进/后退可用性——UI 据此禁用按钮。 */
    private val _canGoBack = MutableStateFlow(false)
    val canGoBack: StateFlow<Boolean> = _canGoBack.asStateFlow()

    private val _canGoForward = MutableStateFlow(false)
    val canGoForward: StateFlow<Boolean> = _canGoForward.asStateFlow()

    /**
     * 初始化 TabManager 并创建首个标签（幂等——tabManager 非空即返回，
     * AD-295 同族口径：可空字段 + ?. 语义由类型系统承载，对优化器免疫）。
     *
     * AD-307：标签 WebView 改 applicationContext 创建（Activity context 在
     * 配置变更重建后泄漏面）；崩溃重建路径不受影响（P0-6 优先宿主 Activity）。
     * AD-326：savedInstanceState 携带会话态（仅 https）时恢复标签——经
     * navigateExternal 安全链路重载，不新增特权入口。
     */
    fun init(
        context: android.content.Context,
        savedInstanceState: android.os.Bundle? = null,
    ) {
        if (tabManager != null) return
        val tm = TabManager()
        tabManager = tm
        val restoredUrls = TabSessionState.restorableUrls(savedInstanceState)
        if (restoredUrls.isNotEmpty()) {
            restoredUrls.forEach { url ->
                val wv = createSecureWebView(context.applicationContext)
                tm.addTab(wv, url = url)
                // 经安全导航链重载（恢复不绕过策略）
                SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(url)
            }
            tm.switchTo(TabSessionState.restorableActiveIndex(savedInstanceState).coerceIn(0, tm.size - 1))
            refresh()
            return
        }
        val initialWebView = createSecureWebView(context.applicationContext)
        SecureWebViewFactory.navigatorFor(initialWebView)?.openTrustedHome()
        tm.addTab(initialWebView, url = BrowserViewModel.HOME_URL)
        refresh()
    }

    /** AD-326：会话态写出——单源在 [TabSessionState]（仅 https 外存）。 */
    fun writeSessionState(outState: android.os.Bundle) = TabSessionState.write(tabManager, outState)

    /** AD-063：地址栏展示映射——首页 file:// 资产路径显示为占位。 */
    internal fun displayAddress(url: String): String =
        if (url.startsWith("file://")) BrowserViewModel.HOME_DISPLAY_URL else url

    /**
     * AD-149（审计 2026-09-23 清单·A6 批）：TabManager 守卫样板单源——
     * init 前调用静默忽略（对齐类内索引操作约定）。
     */
    internal fun withTabManager(block: (TabManager) -> Unit) {
        tabManager?.let(block)
    }

    /** 刷新状态（从 TabManager 同步到 StateFlow）。 */
    fun refresh() {
        withTabManager { tm ->
            _tabs.value = tm.list()
            _activeIndex.value = tm.activeIndex
            // AD-064：前进/后退可用性随刷新点同步（WebView 回调/生命周期均在主线程）
            val currentWebView = tm.current()?.webView
            _canGoBack.value = currentWebView?.canGoBack() ?: false
            _canGoForward.value = currentWebView?.canGoForward() ?: false
            if (!isDraftActive()) {
                setAddress(
                    tm
                        .current()
                        ?.url
                        ?.takeIf { it.isNotBlank() }
                        ?.let { displayAddress(it) }
                        ?: BrowserViewModel.HOME_URL,
                )
            }
        }
    }

    /** 新建标签页。 */
    fun newTab(context: android.content.Context) {
        withTabManager { tm ->
            // 新标签会切换当前 WebView；不能把旧标签的明确批准带入新上下文。
            confirmations.rejectPendingNavigationConfirmation()
            clearDraft()
            // AD-307：applicationContext 创建（Activity context 泄漏面——见 init 注记）
            val wv = createSecureWebView(context.applicationContext)
            SecureWebViewFactory.navigatorFor(wv)?.openTrustedHome()
            tm.addTab(wv, url = BrowserViewModel.HOME_URL)
            refresh()
        }
    }

    /** 切换到指定标签。 */
    fun switchTo(index: Int) {
        withTabManager { tm ->
            if (index !in tm.list().indices) return@withTabManager
            // 待审批状态不得跨标签保留；切换时撤销 Rust 核心的 pending nonce，
            // 回到原标签也需重新请求。
            if (index != tm.activeIndex) {
                confirmations.rejectPendingNavigationConfirmation()
                // 切换标签 = 放弃未提交的地址栏草稿，地址栏显示目标标签 URL
                clearDraft()
            }
            if (tm.switchTo(index)) refresh()
            // AD-215（2026-09-26 审计）：页面错误单槽与当前标签对账——标签 A
            // 的错误不得遮罩切换后的标签 B 内容。
            reconcilePageError()
        }
    }

    /** 关闭指定标签。 */
    fun closeTab(index: Int) {
        withTabManager { tm ->
            if (tm.size <= 1) return@withTabManager
            tm.list().getOrNull(index)?.let { tab ->
                if (confirmations.pendingNavigationConfirmation.value?.webView === tab.webView) {
                    SecureWebViewFactory.navigatorFor(tab.webView)?.rejectPendingNavigation()
                    confirmations.resolvePendingConfirmation(tab.webView)
                }
                // AD-331：归属标签关闭即放弃其待确认下载（WebView 已销毁，
                // 续体入队的落盘目标语境不复存在——fail-closed）
                confirmations.resolvePendingDownload(tab.webView)
                // AD-062（2026-09-24 审计）：不显式 navigator.close()——
                // tabManager.closeTab → tearDown → release 已是单源销毁路径。
            }
            tm.closeTab(index)
            // AD-224（2026-09-26 审计）：关闭标签致 activeIndex 变更时清除地址栏
            // 草稿——与 switchTo 同口径。
            clearDraft()
            // AD-215：关闭标签后对账页面错误单槽（同 switchTo）。
            reconcilePageError()
            refresh()
        }
    }

    /** AD-215：错误遮罩归属标签与当前标签不一致时清除（切换/关闭路径共用）。 */
    private fun reconcilePageError() {
        withTabManager { tm ->
            if (pageErrorWebView() !== tm.current()?.webView) {
                clearPageError()
            }
        }
    }

    /** P1-3 修复：渲染进程崩溃后原位重建 WebView 并重载原 URL（主线程异步执行）。 */
    internal fun rebuildAfterRendererGone(deadWebView: WebView) {
        val context = rebuildContext() ?: return
        launchOnMain {
            withTabManager { tm ->
                val index = tm.list().indexOfFirst { it.webView === deadWebView }
                if (index < 0) return@withTabManager
                val crashedUrl = tm.list()[index].url
                // AD-061（2026-09-24 审计）：销毁收敛 tearDown 单源。
                SecureWebViewFactory.tearDown(deadWebView)
                val fresh = createSecureWebView(context)
                tm.replaceWebView(index, fresh)
                val navigator = SecureWebViewFactory.navigatorFor(fresh)
                if (crashedUrl.isNotBlank() && crashedUrl != BrowserViewModel.HOME_URL) {
                    navigator?.navigateExternal(crashedUrl)
                } else {
                    navigator?.openTrustedHome()
                }
                refresh()
                confirmations.setSecurityNotice(R.string.renderer_restored)
            }
        }
    }

    private fun createSecureWebView(context: android.content.Context): WebView = createWebView(context)
}

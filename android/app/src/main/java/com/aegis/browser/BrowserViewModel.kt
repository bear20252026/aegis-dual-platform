package com.aegis.browser

import android.webkit.WebView
import androidx.lifecycle.ViewModel
import com.aegis.broker.ApprovalRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 浏览器状态 ViewModel（INV-04：BrowserSessionState 是 UI 唯一事实来源）。
 *
 * 专家架构指令：UI 不能以日志、局部 remember、裸回调或全局变量表达地址、
 * 加载、错误、确认、下载、崩溃/恢复等安全状态。所有状态必须来自 ViewModel。
 *
 * 替代 MainActivity 的 remember { mutableStateOf(...) }（违反 INV-04）。
 */
class BrowserViewModel : ViewModel() {
    companion object {
        /** 自定义首页（Android assets 本地加载）。 */
        const val HOME_URL = BrowserEngine.HOME_URL
    }

    private val _tabs = MutableStateFlow<List<Tab>>(emptyList<Tab>())
    val tabs: StateFlow<List<Tab>> = _tabs.asStateFlow()

    private val _activeIndex = MutableStateFlow(0)
    val activeIndex: StateFlow<Int> = _activeIndex.asStateFlow()

    private val _address = MutableStateFlow(HOME_URL)
    val address: StateFlow<String> = _address.asStateFlow()

    private val _tabsPosition = MutableStateFlow("top")
    val tabsPosition: StateFlow<String> = _tabsPosition.asStateFlow()

    private val _webViewAlert = MutableStateFlow<String?>(null)
    val webViewAlert: StateFlow<String?> = _webViewAlert.asStateFlow()

    private val _pendingNavigationConfirmation = MutableStateFlow<PendingNavigationConfirmation?>(null)
    val pendingNavigationConfirmation: StateFlow<PendingNavigationConfirmation?> =
        _pendingNavigationConfirmation.asStateFlow()

    /**
     * 阅读模式 + 整页翻译（ReaderController——单文件单职责；INV-04：
     * 状态经本 ViewModel 层暴露的 StateFlow 流转，UI 不持有浏览器状态）。
     * lazy：首次访问需 init() 已建 tabManager。
     */
    val reader: ReaderController by lazy {
        ReaderController(
            currentWebView = {
                if (::tabManager.isInitialized) tabManager.current()?.webView else null
            },
            currentUrl = {
                if (::tabManager.isInitialized) tabManager.current()?.url else null
            },
            navigateExternal = { url ->
                if (::tabManager.isInitialized) {
                    tabManager.current()?.webView?.let {
                        SecureWebViewFactory.navigatorFor(it)?.navigateExternal(url).orFalse()
                    } ?: false
                } else {
                    false
                }
            },
            alert = { message -> _webViewAlert.value = message },
        )
    }

    private lateinit var tabManager: TabManager

    /** 初始化 TabManager 并创建首个标签。 */
    fun init(context: android.content.Context) {
        if (::tabManager.isInitialized) return
        tabManager = TabManager()
        val initialWebView = createSecureWebView(context)
        SecureWebViewFactory.navigatorFor(initialWebView)?.openTrustedHome()
        tabManager.addTab(initialWebView, url = HOME_URL)
        refresh()
    }

    /** 刷新状态（从 TabManager 同步到 StateFlow）。 */
    fun refresh() {
        if (!::tabManager.isInitialized) return
        _tabs.value = tabManager.list()
        _activeIndex.value = tabManager.activeIndex
        _address.value = tabManager.current()?.url ?: HOME_URL
    }

    /** 新建标签页。 */
    fun newTab(context: android.content.Context) {
        if (!::tabManager.isInitialized) return
        // 新标签会切换当前 WebView；不能把旧标签的明确批准带入新上下文。
        rejectPendingNavigationConfirmation()
        val wv = createSecureWebView(context)
        SecureWebViewFactory.navigatorFor(wv)?.openTrustedHome()
        tabManager.addTab(wv, url = HOME_URL)
        refresh()
    }

    /** 切换到指定标签。 */
    fun switchTo(index: Int) {
        if (!::tabManager.isInitialized) return
        if (index !in tabManager.list().indices) return
        // 待审批状态不得跨标签保留；切换时撤销 Rust 核心的 pending nonce，回到原标签也需重新请求。
        if (index != tabManager.activeIndex) rejectPendingNavigationConfirmation()
        if (tabManager.switchTo(index)) refresh()
    }

    /** 关闭指定标签。 */
    fun closeTab(index: Int) {
        if (!::tabManager.isInitialized || tabManager.size <= 1) return
        tabManager.list().getOrNull(index)?.let { tab ->
            if (_pendingNavigationConfirmation.value?.webView === tab.webView) {
                SecureWebViewFactory.navigatorFor(tab.webView)?.rejectPendingNavigation()
                _pendingNavigationConfirmation.value = null
            }
            SecureWebViewFactory.navigatorFor(tab.webView)?.close()
        }
        tabManager.closeTab(index)
        refresh()
    }

    /** 更新地址栏内容。 */
    fun updateAddress(newAddress: String) {
        _address.value = newAddress
    }

    /** 导航到地址栏 URL。 */
    fun navigateToAddress() {
        if (!::tabManager.isInitialized) return
        val wv = tabManager.current()?.webView ?: return
        if (!SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(_address.value).orFalse()) {
            _webViewAlert.value = "该地址无法通过安全策略验证"
        }
    }

    /** 历史导航（后退/前进/刷新——合并减少函数数——detekt TooManyFunctions）。 */
    fun navigateHistory(action: HistoryAction) {
        val wv = tabManager.current()?.webView ?: return
        if (!SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(action).orFalse()) {
            _webViewAlert.value = "当前标签没有可执行的历史导航操作"
        }
    }

    /** 设置/清除安全提示（null = 清除）。 */
    fun setWebViewAlert(message: String?) {
        _webViewAlert.value = message
    }

    /**
     * Compose 的明确批准操作。只允许当前活动标签的待审批请求恢复导航，防止标签切换后
     * 在错误 WebView 上消费授权；客户端仍会在恢复前调用 Rust 核心批准并消费。
     */
    fun approvePendingNavigationConfirmation(): Boolean {
        val pending = _pendingNavigationConfirmation.value ?: return false
        if (!::tabManager.isInitialized || tabManager.current()?.webView !== pending.webView) {
            _webViewAlert.value = "请先切换回发起确认请求的标签。"
            return false
        }
        _pendingNavigationConfirmation.value = null
        val approved =
            SecureWebViewFactory
                .navigatorFor(pending.webView)
                ?.approvePendingNavigation() == true
        if (!approved) _webViewAlert.value = "确认请求已失效、被拒绝或无法安全恢复导航。"
        return approved
    }

    /** 对话框关闭、返回键或拒绝按钮一律走此入口；失败不会恢复导航。 */
    fun rejectPendingNavigationConfirmation(): Boolean {
        val pending = _pendingNavigationConfirmation.value ?: return false
        _pendingNavigationConfirmation.value = null
        return SecureWebViewFactory.navigatorFor(pending.webView)?.rejectPendingNavigation() == true
    }

    /** 获取 TabManager 实例（供 WebContentArea 使用）。 */
    fun getTabManager(): TabManager? = if (::tabManager.isInitialized) tabManager else null

    private fun createSecureWebView(context: android.content.Context): WebView =
        SecureWebViewFactory.create(
            context = context,
            onNavigationConfirmationRequested = { webView, request ->
                _pendingNavigationConfirmation.value = PendingNavigationConfirmation(webView, request)
            },
            onNavigationConfirmationResolved = { webView ->
                if (_pendingNavigationConfirmation.value?.webView === webView) {
                    _pendingNavigationConfirmation.value = null
                }
            },
        )
}

/** 仅 ViewModel 保存发起 WebView 引用；Compose 仅显示 request 的最小绑定字段。 */
data class PendingNavigationConfirmation internal constructor(
    internal val webView: WebView,
    val request: ApprovalRequest,
)

private fun Boolean?.orFalse(): Boolean = this ?: false

/** 历史导航动作。 */
enum class HistoryAction { BACK, FORWARD, RELOAD }

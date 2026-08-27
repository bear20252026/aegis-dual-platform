package com.aegis.browser

import androidx.lifecycle.ViewModel
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

    private lateinit var tabManager: TabManager

    /** 初始化 TabManager 并创建首个标签。 */
    fun init(context: android.content.Context) {
        if (::tabManager.isInitialized) return
        tabManager = TabManager()
        val initialWebView = SecureWebViewFactory.create(context)
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
        val wv = SecureWebViewFactory.create(context)
        SecureWebViewFactory.navigatorFor(wv)?.openTrustedHome()
        tabManager.addTab(wv, url = HOME_URL)
        refresh()
    }

    /** 切换到指定标签。 */
    fun switchTo(index: Int) {
        if (!::tabManager.isInitialized) return
        tabManager.switchTo(index)
        refresh()
    }

    /** 关闭指定标签。 */
    fun closeTab(index: Int) {
        if (!::tabManager.isInitialized || tabManager.size <= 1) return
        tabManager.list().getOrNull(index)?.let { tab ->
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

    /** 获取 TabManager 实例（供 WebContentArea 使用）。 */
    fun getTabManager(): TabManager? = if (::tabManager.isInitialized) tabManager else null
}

private fun Boolean?.orFalse(): Boolean = this ?: false

/** 历史导航动作。 */
enum class HistoryAction { BACK, FORWARD, RELOAD }

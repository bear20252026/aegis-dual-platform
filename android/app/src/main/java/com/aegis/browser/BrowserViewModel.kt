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
    private val _tabs = MutableStateFlow<List<TabState>>(emptyList())
    val tabs: StateFlow<List<TabState>> = _tabs.asStateFlow()

    private val _activeIndex = MutableStateFlow(0)
    val activeIndex: StateFlow<Int> = _activeIndex.asStateFlow()

    private val _address = MutableStateFlow("https://www.bing.com")
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
        com.aegis.browser
            .BrowserEngine(initialWebView)
            .load("https://www.bing.com")
        tabManager.addTab(initialWebView, url = "https://www.bing.com")
        refresh()
    }

    /** 刷新状态（从 TabManager 同步到 StateFlow）。 */
    fun refresh() {
        if (!::tabManager.isInitialized) return
        _tabs.value = tabManager.list()
        _activeIndex.value = tabManager.activeIndex
        _address.value = tabManager.current()?.url ?: "https://www.bing.com"
    }

    /** 新建标签页。 */
    fun newTab(context: android.content.Context) {
        if (!::tabManager.isInitialized) return
        val wv = SecureWebViewFactory.create(context)
        com.aegis.browser
            .BrowserEngine(wv)
            .load("https://www.bing.com")
        tabManager.addTab(wv, url = "https://www.bing.com")
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
        if (!::tabManager.isInitialized) return
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
        com.aegis.browser
            .BrowserEngine(wv)
            .load(_address.value)
    }

    /** 后退。 */
    fun goBack() {
        tabManager.current()?.webView?.goBack()
    }

    /** 前进。 */
    fun goForward() {
        tabManager.current()?.webView?.goForward()
    }

    /** 刷新当前页。 */
    fun reload() {
        tabManager.current()?.webView?.reload()
    }

    /** 设置安全提示（System WebView 版本过旧）。 */
    fun setWebViewAlert(message: String?) {
        _webViewAlert.value = message
    }

    /** 清除安全提示。 */
    fun dismissWebViewAlert() {
        _webViewAlert.value = null
    }

    /** 获取 TabManager 实例（供 WebContentArea 使用）。 */
    fun getTabManager(): TabManager? = if (::tabManager.isInitialized) tabManager else null
}

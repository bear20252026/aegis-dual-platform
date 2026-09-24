package com.aegis.browser

import android.webkit.WebView
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * 浏览器状态 ViewModel（INV-04：BrowserSessionState 是 UI 唯一事实来源）。
 *
 * 专家架构指令：UI 不能以日志、局部 remember、裸回调或全局变量表达地址、
 * 加载、错误、确认、下载、崩溃/恢复等安全状态。所有状态必须来自 ViewModel。
 *
 * 替代 MainActivity 的 remember { mutableStateOf(...) }（违反 INV-04）。
 */
class BrowserViewModel(
    private val broker: AndroidBroker,
) : ViewModel() {
    companion object {
        /** 自定义首页（Android assets 本地加载）。 */
        const val HOME_URL = BrowserEngine.HOME_URL

        /** 「打开」按钮防抖间隔（毫秒）——P2 修复（全量复审 2026-09-01）。 */
        const val NAVIGATE_DEBOUNCE_MS = 500L

        /**
         * AD-063（2026-09-24 审计）：首页的地址栏展示形态。首页是本地资产
         * `file:///android_asset/start.html`——原样显示 file:// 原始 URL
         * （用户可编辑提交 → 必被策略拒绝，误导）且泄露内部路径结构。
         */
        const val HOME_DISPLAY_URL = "aegis://home"

        /** AD-033：日志用标题截断上限（防日志洪泛）。 */
        private const val TITLE_LOG_MAX_LENGTH = 120

        /**
         * 架构解耦（第 5 项）：broker 由组合根注入 ViewModel（再透传 SecureWebViewFactory）
         * ——Application 的强转定位收敛到这一个工厂点，其余层不再 `(context as
         * AegisApplication)` 取 broker。
         */
        fun factory(application: android.app.Application): androidx.lifecycle.ViewModelProvider.Factory =
            object : androidx.lifecycle.ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T {
                    val app = application as AegisApplication
                    return BrowserViewModel(app.broker) as T
                }
            }
    }

    private val _tabs = MutableStateFlow<List<Tab>>(emptyList<Tab>())
    val tabs: StateFlow<List<Tab>> = _tabs.asStateFlow()

    private val _activeIndex = MutableStateFlow(0)
    val activeIndex: StateFlow<Int> = _activeIndex.asStateFlow()

    private val _address = MutableStateFlow(HOME_URL)
    val address: StateFlow<String> = _address.asStateFlow()

    /**
     * P2 修复（全量复审 2026-09-01）：地址栏编辑草稿标记——用户输入未提交时，
     * 标签切换 / 后台页面事件不得覆盖输入内容（原先 _address 全局单字段被
     * refresh()/onPageUrlObserved 直接覆盖，多标签下互相踩踏）。
     * 提交（navigateToAddress）或切换标签即清除草稿，恢复派生自 Tab.url。
     */
    private var addressDraftActive = false

    private val _tabsPosition = MutableStateFlow("top")
    val tabsPosition: StateFlow<String> = _tabsPosition.asStateFlow()

    private val _webViewAlert = MutableStateFlow<String?>(null)
    val webViewAlert: StateFlow<String?> = _webViewAlert.asStateFlow()

    private val _pendingNavigationConfirmation = MutableStateFlow<PendingNavigationConfirmation?>(null)
    val pendingNavigationConfirmation: StateFlow<PendingNavigationConfirmation?> =
        _pendingNavigationConfirmation.asStateFlow()

    /**
     * P2-1 修复（全面审计 2026-09-04）：页面级错误状态（SSL 证书失败 / 主框架
     * 加载失败 / 主框架 HTTP >= 400；null = 无错误）。INV-04：错误状态经
     * ViewModel StateFlow 流转，UI 只渲染不持有（原实现无任何错误回调——
     * 证书错误/DNS 失败一律静默白屏）。
     */
    private val _pageError = MutableStateFlow<PageError?>(null)
    val pageError: StateFlow<PageError?> = _pageError.asStateFlow()

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

    /** P1-3 修复：渲染进程崩溃重建 WebView 需要 Context（init 时存应用级引用）。 */
    private var appContext: android.content.Context? = null

    /**
     * 宿主 Activity 弱引用（P0-5 修复（全面审计 2026-09-04）——P0-6 崩溃
     * 重建需要主题化 Activity context 创建 WebView）。@Volatile：写入仅在
     * 主线程生命周期回调（attach/detach），读可能来自渲染崩溃回调链。
     */
    @Volatile
    private var hostActivityRef: java.lang.ref.WeakReference<android.app.Activity>? = null

    /** P0-5 修复（全面审计 2026-09-04）：MainActivity onCreate 注入宿主引用。 */
    fun attachActivity(activity: android.app.Activity) {
        hostActivityRef = java.lang.ref.WeakReference(activity)
    }

    /**
     * P0-5 修复（全面审计 2026-09-04）：MainActivity onDestroy 且 isFinishing
     * 时解除引用（配置变更重建绝不 detach——新 Activity 会重新 attach）。
     * 弱引用持有，不阻止 Activity 被 GC。
     */
    fun detachActivity() {
        hostActivityRef = null
    }

    /** 可用的宿主 Activity（已 finish/destroy 的引用视为不可用，返回 null）。 */
    private fun hostActivityOrNull(): android.app.Activity? {
        val candidate = hostActivityRef?.get() ?: return null
        return candidate.takeUnless { it.isFinishing || it.isDestroyed }
    }

    /** 当前标签的 WebView（系统回退键消费 WebView 历史栈——未初始化返回 null）。 */
    fun currentWebViewOrNull(): WebView? = if (::tabManager.isInitialized) tabManager.current()?.webView else null

    /** 初始化 TabManager 并创建首个标签。 */
    fun init(context: android.content.Context) {
        if (::tabManager.isInitialized) return
        appContext = context.applicationContext
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
        if (!addressDraftActive) {
            _address.value =
                tabManager
                    .current()
                    ?.url
                    ?.takeIf { it.isNotBlank() }
                    ?.let(::displayAddress)
                    ?: HOME_URL
        }
    }

    /**
     * AD-063：地址栏展示映射——首页 file:// 资产路径显示为 [HOME_DISPLAY_URL]
     * 占位（可编辑性不受影响：用户改动即走 updateAddress 草稿路径）。
     */
    private fun displayAddress(url: String): String = if (url.startsWith("file://")) HOME_DISPLAY_URL else url

    /** 新建标签页。 */
    fun newTab(context: android.content.Context) {
        if (!::tabManager.isInitialized) return
        // 新标签会切换当前 WebView；不能把旧标签的明确批准带入新上下文。
        rejectPendingNavigationConfirmation()
        addressDraftActive = false
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
        if (index != tabManager.activeIndex) {
            rejectPendingNavigationConfirmation()
            // 切换标签 = 放弃未提交的地址栏草稿，地址栏显示目标标签 URL
            addressDraftActive = false
        }
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
            // AD-062（2026-09-24 审计）：删除此处显式 navigator.close()——
            // tabManager.closeTab → tearDown → release → navigator.close()
            // 已是单源销毁路径，此前 destroySession 被调用两次（幂等但语义
            // 漂移：显式 close 之后 tearDown 的 release 已拿不到导航器）。
        }
        tabManager.closeTab(index)
        refresh()
    }

    /** 更新地址栏内容（编辑草稿——未提交前不受标签切换/页面事件覆盖）。 */
    fun updateAddress(newAddress: String) {
        addressDraftActive = true
        _address.value = newAddress
    }

    /** 导航到地址栏 URL。 */
    fun navigateToAddress() {
        navigateWithDebounce(bypassDebounce = false)
    }

    /**
     * 导航共享实现。AD-048（2026-09-24 审计）：防抖仅保护地址栏「打开」按钮
     * 连点；外链 intent（其他 App「用 Aegis 打开」）是用户明确的单次意图，
     * 被防抖静默吞掉属缺陷——经 [bypassDebounce] 绕过，安全链路（broker
     * 决策）不绕过。
     */
    private fun navigateWithDebounce(bypassDebounce: Boolean) {
        val wv = if (::tabManager.isInitialized) tabManager.current()?.webView else null
        if (wv == null || (!bypassDebounce && !navigateDebounceOk())) return
        val target = _address.value
        // 提交即清除草稿：后续 onPageStarted→onPageUrlObserved 正常同步地址栏
        addressDraftActive = false
        if (!SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(target).orFalse()) {
            _webViewAlert.value = "该地址无法通过安全策略验证"
        }
    }

    /**
     * P1-4 修复（全面审计批次4）：外链 intent 消费——Manifest 声明了
     * http/https VIEW intent-filter，但此前无 intent?.data 读取、无
     * onNewIntent：其他 App「用 Aegis 打开」只落到首页，URL 静默丢失。
     * 经地址栏同一安全链路（归一 + OriginPolicy + broker），
     * 非法 scheme 走既有拒绝反馈（fail-closed），不新增特权入口。
     *
     * AD-048：外链绕过防抖——防抖防的是按钮连点，不是用户单次明确意图。
     */
    fun openExternalUrl(url: String?) {
        if (url.isNullOrBlank()) return
        _address.value = url
        navigateWithDebounce(bypassDebounce = true)
    }

    /**
     * P2 修复（全量复审 2026-09-01）：导航防抖——待审批确认期间忽略重复提交
     * （连点会撤销待确认 nonce 并触发误导性提示）；[NAVIGATE_DEBOUNCE_MS]
     * 内重复点击忽略。单出口无提前 return（detekt ReturnCount/MagicNumber）。
     */
    private fun navigateDebounceOk(): Boolean {
        val noPendingConfirmation = _pendingNavigationConfirmation.value == null
        val elapsed = android.os.SystemClock.uptimeMillis() - lastNavigateAttemptAt
        val allowed = noPendingConfirmation && elapsed >= NAVIGATE_DEBOUNCE_MS
        if (allowed) lastNavigateAttemptAt = android.os.SystemClock.uptimeMillis()
        return allowed
    }

    private var lastNavigateAttemptAt = 0L

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
     * P2-1 修复（全面审计 2026-09-04）：清除页面错误面板。新导航开始
     * （onPageStarted → URL 变化）时由 [createSecureWebView] 的回调自动触发，
     * 重试 / 返回安全页按钮也走此入口，保证旧错误不残留。
     */
    fun clearPageError() {
        _pageError.value = null
    }

    /** P2-1 修复：错误面板「重试」——清错误状态后 reload 当前标签。 */
    fun retryCurrentPage() {
        clearPageError()
        navigateHistory(HistoryAction.RELOAD)
    }

    /** P2-1 修复：错误面板「返回安全页」——当前标签回到受信首页。 */
    fun returnToSafeHome() {
        val wv = if (::tabManager.isInitialized) tabManager.current()?.webView else null
        clearPageError()
        SecureWebViewFactory.navigatorFor(wv ?: return)?.openTrustedHome()
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

    /** P1-3 修复：渲染进程崩溃后原位重建 WebView 并重载原 URL（主线程异步执行）。 */
    private fun rebuildAfterRendererGone(deadWebView: WebView) {
        // P0-6 修复（全面审计 2026-09-04）：优先用宿主 Activity context 创建
        // WebView——appContext（无主题）创建的 WebView 一弹原生对话框
        // （<select>/日期选择等）即崩（token null）。
        val context = resolveRebuildContext() ?: return
        // AD-059（2026-09-24 审计）：裸 Handler → viewModelScope（生命周期感知
        // ——ViewModel 清除后重建任务自动取消，不再有游离主线程回调）。
        viewModelScope.launch(Dispatchers.Main) {
            if (!::tabManager.isInitialized) return@launch
            val index = tabManager.list().indexOfFirst { it.webView === deadWebView }
            if (index < 0) return@launch
            val crashedUrl = tabManager.list()[index].url
            // AD-061（2026-09-24 审计）：手写 release+destroy 绕过统一销毁序列
            // （缺 stopLoading/about:blank 置空步骤）——收敛到 tearDown 单源。
            SecureWebViewFactory.tearDown(deadWebView)
            val fresh = createSecureWebView(context)
            tabManager.replaceWebView(index, fresh)
            val navigator = SecureWebViewFactory.navigatorFor(fresh)
            if (crashedUrl.isNotBlank() && crashedUrl != HOME_URL) {
                navigator?.navigateExternal(crashedUrl)
            } else {
                navigator?.openTrustedHome()
            }
            refresh()
            _webViewAlert.value = "页面进程已恢复，正在重新加载"
        }
    }

    /**
     * P0-6 修复（全面审计 2026-09-04）：崩溃重建 context 解析——优先宿主
     * Activity；拿不到（配置变更重建间隙 / 已退出 detach）回退 appContext
     * 并 Log.w 留痕（此路径下页面原生对话框不可用，属已知降级）。
     */
    private fun resolveRebuildContext(): android.content.Context? {
        val activity = hostActivityOrNull()
        if (activity != null) return activity
        android.util.Log.w("Aegis", "P0-6: 崩溃重建拿不到宿主 Activity，回退 appContext（原生对话框可能不可用）")
        return appContext
    }

    /**
     * AD-033：日志用标题净化——剥掉换行/回退（防 logcat 多行伪造）、压缩
     * 空白、截断到 120 字符（防日志洪泛）。Tab.title 仍存原文（UI 显示语义）。
     */
    private fun sanitizeTitleForLog(title: String): String =
        title
            .replace(Regex("[\\r\\n\\t]+"), " ")
            .take(TITLE_LOG_MAX_LENGTH)

    private fun createSecureWebView(context: android.content.Context): WebView =
        SecureWebViewFactory.create(
            broker = broker,
            context = context,
            onNavigationConfirmationRequested = { webView, request ->
                _pendingNavigationConfirmation.value = PendingNavigationConfirmation(webView, request)
            },
            onNavigationConfirmationResolved = { webView ->
                if (_pendingNavigationConfirmation.value?.webView === webView) {
                    _pendingNavigationConfirmation.value = null
                }
            },
            onNavigationDenied = { _, code, _ ->
                // P0 修复（全量复审 2026-09-01）：顶层导航被拒不再静默——经
                // webViewAlert 上抛 UI（此前用户只看到白屏/无反应）。
                _webViewAlert.value =
                    when (code) {
                        "session_expired" -> "浏览会话已过期，已自动续期失败——请重试或新建标签"
                        else -> "该地址无法通过安全策略验证（$code）"
                    }
            },
            onPageUrlObserved = { webView, url ->
                // P1-6 修复（全量复审 2026-09-01）：地址栏随实际页面同步。
                // P2 修复：用户编辑草稿期间不覆盖输入（提交后恢复正常同步）。
                // P2-1 修复（全面审计 2026-09-04）：onPageStarted → URL 变化即
                // 清除错误面板（重试/新导航开始后旧错误不残留）。
                if (tabManager.current()?.webView === webView) {
                    _pageError.value = null
                }
                if (url.isNotBlank()) {
                    // AD-036（2026-09-24 审计）：原地改 var url 不触发 StateFlow
                    // （self-equals）——收敛到 TabManager.updateUrl copy 单写点
                    // （与 updateTitle 同模式）。
                    tabManager.list().firstOrNull { it.webView === webView }?.let {
                        tabManager.updateUrl(it.id, url)
                    }
                    if (!addressDraftActive && tabManager.current()?.webView === webView) {
                        _address.value = displayAddress(url)
                    }
                }
            },
            onTitleObserved = { webView, title ->
                // P0 修复（全库审计 2026-09-02）：页面标题回填 Tab.title——
                // 此前 onReceivedTitle 仅打日志，标签栏永远显示「新标签页」。
                // P0 修复2（真机复测 2026-09-02）：原地改 var title 后 refresh()
                // 不触发发射——list() 快照与 StateFlow 旧值持同一 Tab 实例，
                // data class self-equals 恒 true。收敛到 TabManager.updateTitle
                // （copy 替换实例）单写点。
                if (title.isNotBlank()) {
                    val target = tabManager.list().firstOrNull { it.webView === webView }
                    // AD-033（2026-09-24 审计）：页面标题是远端可控输入——
                    // 换行可伪造多行日志（logcat 注入），截断防日志洪泛。
                    android.util.Log.i("Aegis", "R12 titleHit tab=${target?.id} title=${sanitizeTitleForLog(title)}")
                    target?.let { tabManager.updateTitle(it.id, title) }
                    refresh()
                }
            },
            onRendererGone = { deadWebView ->
                // P1-3 修复（全量复审 2026-09-01）：渲染进程崩溃后重建当前标签
                // 的 WebView 并重载原 URL（原 no-op——标签永久白屏）。
                rebuildAfterRendererGone(deadWebView)
            },
            onPageError = { webView, description, isSsl, url ->
                // P2-1 修复（全面审计 2026-09-04）：仅当前活动标签的错误上屏
                // （后台标签的加载失败不遮蔽当前页内容）。
                if (tabManager.current()?.webView === webView) {
                    _pageError.value =
                        PageError(
                            description = description,
                            isSsl = isSsl,
                            url = url,
                        )
                }
            },
        )
}

/** 仅 ViewModel 保存发起 WebView 引用；Compose 仅显示 request 的最小绑定字段。 */
data class PendingNavigationConfirmation internal constructor(
    internal val webView: WebView,
    val request: ApprovalRequest,
)

/**
 * P2-1 修复（全面审计 2026-09-04）：页面级错误（不可变数据类）。
 *
 * @param description 简短中文错误说明（错误面板主文案）
 * @param isSsl       是否为 SSL 证书错误（面板标题区分「安全连接失败」）
 * @param url         出错页面的 URL（面板展示定位）
 */
data class PageError(
    val description: String,
    val isSsl: Boolean,
    val url: String,
)

private fun Boolean?.orFalse(): Boolean = this ?: false

/** 历史导航动作。 */
enum class HistoryAction { BACK, FORWARD, RELOAD }

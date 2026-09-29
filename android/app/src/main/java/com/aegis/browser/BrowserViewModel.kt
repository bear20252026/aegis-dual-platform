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
 *
 * AD-103（审计 2026-09-23 清单·A6 批）：文件超改造红线——页面事件装配体
 * 抽 [WebViewEventAssembly]，错误码文案映射抽 [PageErrorTexts]，状态模型
 * 抽 BrowserModels.kt；本类只保留状态、用户意图入口与崩溃重建。
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

        /**
         * 架构解耦（第 5 项）：broker 由组合根注入 ViewModel（再透传
         * WebViewEventAssembly）——Application 的强转定位收敛到这一个工厂点。
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

    /**
     * AD-064（2026-09-24 审计）：前进/后退可用性——UI 据此禁用按钮（原始终
     * 可点，无可历史时点了静默无反馈）。经 [refresh] 随标签切换/页面事件刷新。
     */
    private val _canGoBack = MutableStateFlow(false)
    val canGoBack: StateFlow<Boolean> = _canGoBack.asStateFlow()

    private val _canGoForward = MutableStateFlow(false)
    val canGoForward: StateFlow<Boolean> = _canGoForward.asStateFlow()

    private val _address = MutableStateFlow(HOME_URL)
    val address: StateFlow<String> = _address.asStateFlow()

    /**
     * P2 修复（全量复审 2026-09-01）：地址栏编辑草稿标记——用户输入未提交时，
     * 标签切换 / 后台页面事件不得覆盖输入内容（原先 _address 全局单字段被
     * refresh()/onPageUrlObserved 直接覆盖，多标签下互相踩踏）。
     * 提交（navigateToAddress）或切换标签即清除草稿，恢复派生自 Tab.url。
     *
     * AD-209（审计 2026-09-23 清单·A7 批）：单线程意图显式声明——本标记
     * 与各 StateFlow 同属「仅主线程读写」约束（写入点全部在 Activity
     * 生命周期/主线程回调链与 viewModelScope(Main) 协程；StateFlow 写入
     * 本身可见，无需 AtomicBoolean 加重语义）。若未来引入后台写路径，
     * 必须先迁移到原子类型或收敛到单写点协程。
     */
    private var addressDraftActive = false

    /** AD-103 配套：导航防抖独立小类（NavigateDebounce——锚点状态内聚）。 */
    private val navigateDebounce = NavigateDebounce(NAVIGATE_DEBOUNCE_MS)

    /**
     * AD-152（审计 2026-09-23 清单·A7 批）：布局态走 [TabsPosition] 枚举
     * （原魔法字符串 "top"/"left"——typo 静默走默认分支，编译期无守护）。
     */
    private val _tabsPosition = MutableStateFlow(TabsPosition.TOP)
    val tabsPosition: StateFlow<TabsPosition> = _tabsPosition.asStateFlow()

    /**
     * AD-251（2026-09-26 审计）：布局切换入口——chrome 布局按钮切换
     * top/left；MainActivity 两种布局均含地址栏（接线见 onToggleLayout）。
     */
    fun toggleTabsPosition() {
        _tabsPosition.value =
            if (_tabsPosition.value == TabsPosition.TOP) TabsPosition.LEFT else TabsPosition.TOP
    }

    private val _webViewAlert = MutableStateFlow<String?>(null)
    val webViewAlert: StateFlow<String?> = _webViewAlert.asStateFlow()

    private val _pendingNavigationConfirmation = MutableStateFlow<PendingNavigationConfirmation?>(null)
    val pendingNavigationConfirmation: StateFlow<PendingNavigationConfirmation?> =
        _pendingNavigationConfirmation.asStateFlow()

    /**
     * P2-1 修复（全面审计 2026-09-04）：页面级错误状态（SSL 证书失败 / 主框架
     * 加载失败 / 主框架 HTTP >= 400；null = 无错误）。INV-04：错误状态经
     * ViewModel StateFlow 流转，UI 只渲染不持有。
     */
    private val _pageError = MutableStateFlow<PageError?>(null)
    val pageError: StateFlow<PageError?> = _pageError.asStateFlow()

    /**
     * 阅读模式 + 整页翻译（ReaderController——单文件单职责；INV-04）。
     * AD-196（审计 2026-09-23 清单·A7 批）：显式构造取代 lazy——控制器构造
     * 仅捕获回调 lambda（回调执行时才经 [getTabManager] 取当前 WebView），
     * 构造期初始化后时序不再依赖「首次访问在 init 之后」的隐性契约
     * （UI 早触发安全降级为 null 当前 WebView）。
     */
    val reader: ReaderController =
        ReaderController(
            currentWebView = { getTabManager()?.current()?.webView },
            currentUrl = { getTabManager()?.current()?.url },
            navigateExternal = { url ->
                val wv = getTabManager()?.current()?.webView
                wv != null && SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(url).orFalse()
            },
            // AD-228（2026-09-26 审计）：页面功能提示经资源 id 上抛，文案
            // 收敛 strings.xml 单源。
            alertRes = { res -> _webViewAlert.value = alertText(res) },
        )

    // AD-003 R8 真机回归（2026-09-29）：lateinit 换可空字段。 lateinit 的
    // `::x.isInitialized` 在字节码层退化为字段空比较——R8 full mode 按
    // @NotNull 声明把该比较折叠为 true，连 init() 开头的幂等检查
    // `if (isInitialized) return` 也被折叠成无条件 return → tabManager 永不
    // 初始化 → 启动即崩（retrace 实锤：Required value was null at
    // AddressAndContent:248；整类 keep 不缓解）。可空字段 + ?./?: 语义由
    // 类型系统承载，对优化器免疫（等价语义：未初始化 = null）。
    private var tabManager: TabManager? = null

    /** P1-3 修复：渲染进程崩溃重建 WebView 需要 Context（init 时存应用级引用）。 */
    private var appContext: android.content.Context? = null

    /** AD-103 配套：宿主绑定（弱引用 + 版本检查去重）独立小类（HostActivityBindings）。 */
    private val hostBindings = HostActivityBindings()

    /** AD-239：版本检查单次触发（去重标记在 HostActivityBindings——跨重建不重复）。 */
    fun checkWebViewVersionOnce(onOutdated: (String) -> Unit) {
        hostBindings.checkWebViewVersionOnce(appContext, onOutdated)
    }

    /** P0-5 修复：MainActivity onCreate 注入宿主引用（弱引用）。 */
    fun attachActivity(activity: android.app.Activity) {
        hostBindings.attach(activity)
    }

    /** P0-5 修复：MainActivity onDestroy 且 isFinishing 时解除引用。 */
    fun detachActivity() {
        hostBindings.detach()
    }

    /** 当前标签的 WebView（系统回退键消费 WebView 历史栈——未初始化返回 null）。 */
    fun currentWebViewOrNull(): WebView? = tabManager?.current()?.webView

    /**
     * AD-063：地址栏展示映射——首页 file:// 资产路径显示为 [HOME_DISPLAY_URL]
     * 占位（可编辑性不受影响：用户改动即走 updateAddress 草稿路径）。
     */
    private fun displayAddress(url: String): String = if (url.startsWith("file://")) HOME_DISPLAY_URL else url

    /**
     * AD-149（审计 2026-09-23 清单·A6 批）：TabManager 守卫样板单源——
     * `if (!::tabManager.isInitialized) return` 此前散落 8+ 处，收敛为本
     * 收口；init 前调用静默忽略（对齐类内索引操作约定）。
     */
    private fun withTabManager(block: (TabManager) -> Unit) {
        tabManager?.let(block)
    }

    /** 初始化 TabManager 并创建首个标签。 */
    fun init(context: android.content.Context) {
        if (tabManager != null) return
        appContext = context.applicationContext
        val tm = TabManager()
        tabManager = tm
        val initialWebView = createSecureWebView(context)
        SecureWebViewFactory.navigatorFor(initialWebView)?.openTrustedHome()
        tm.addTab(initialWebView, url = HOME_URL)
        refresh()
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
            if (!addressDraftActive) {
                _address.value =
                    tm
                        .current()
                        ?.url
                        ?.takeIf { it.isNotBlank() }
                        ?.let { displayAddress(it) }
                        ?: HOME_URL
            }
        }
    }

    /** 新建标签页。 */
    fun newTab(context: android.content.Context) {
        withTabManager { tm ->
            // 新标签会切换当前 WebView；不能把旧标签的明确批准带入新上下文。
            rejectPendingNavigationConfirmation()
            addressDraftActive = false
            val wv = createSecureWebView(context)
            SecureWebViewFactory.navigatorFor(wv)?.openTrustedHome()
            tm.addTab(wv, url = HOME_URL)
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
                rejectPendingNavigationConfirmation()
                // 切换标签 = 放弃未提交的地址栏草稿，地址栏显示目标标签 URL
                addressDraftActive = false
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
                if (_pendingNavigationConfirmation.value?.webView === tab.webView) {
                    SecureWebViewFactory.navigatorFor(tab.webView)?.rejectPendingNavigation()
                    _pendingNavigationConfirmation.value = null
                }
                // AD-062（2026-09-24 审计）：不显式 navigator.close()——
                // tabManager.closeTab → tearDown → release 已是单源销毁路径。
            }
            tm.closeTab(index)
            // AD-224（2026-09-26 审计）：关闭标签致 activeIndex 变更时清除地址栏
            // 草稿——与 switchTo 同口径。
            addressDraftActive = false
            // AD-215：关闭标签后对账页面错误单槽（同 switchTo）。
            reconcilePageError()
            refresh()
        }
    }

    /** AD-215：错误遮罩归属标签与当前标签不一致时清除（切换/关闭路径共用）。 */
    private fun reconcilePageError() {
        withTabManager { tm ->
            if (_pageError.value?.webView !== tm.current()?.webView) {
                _pageError.value = null
            }
        }
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
     * 连点；外链 intent 是用户明确的单次意图，经 [bypassDebounce] 绕过，
     * 安全链路（broker 决策）不绕过。
     */
    private fun navigateWithDebounce(bypassDebounce: Boolean) {
        val wv = tabManager?.current()?.webView
        if (wv == null ||
            (!bypassDebounce && !navigateDebounce.ok(_pendingNavigationConfirmation.value != null))
        ) {
            return
        }
        // AD-238（2026-09-26 审计）：地址栏停留首页占位（用户未编辑）时点
        // 「打开」——占位 aegis://home 不可导航，映射回 HOME_URL（等价刷新）。
        val target = if (_address.value == HOME_DISPLAY_URL) HOME_URL else _address.value
        // AD-111（审计 2026-09-23 清单·A6 批）：空输入静默 no-op——原实现空串
        // 会走完归一链被拒后弹「无法通过安全策略验证」恐吓提示（用户只是清空
        // 后误触「打开」）。空输入无导航意图，静默返回不提示。
        if (target.isBlank()) return
        // 提交即清除草稿：后续 onPageStarted→onPageUrlObserved 正常同步地址栏
        addressDraftActive = false
        val navigated = SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(target).orFalse()
        if (!navigated &&
            // AD-216（2026-09-26 审计）：RequireConfirmation「待确认」与 Deny
            // 「被拒」共用 false 返回——确认对话框已挂起时不得再弹恐吓提示。
            _pendingNavigationConfirmation.value == null
        ) {
            _webViewAlert.value = alertText(R.string.nav_rejected)
        }
    }

    /**
     * P1-4 修复（全面审计批次4）：外链 intent 消费——经地址栏同一安全链路
     * （归一 + OriginPolicy + broker），非法 scheme 走既有拒绝反馈
     * （fail-closed），不新增特权入口。AD-048：外链绕过防抖。
     */
    fun openExternalUrl(url: String?) {
        if (url.isNullOrBlank()) return
        _address.value = url
        navigateWithDebounce(bypassDebounce = true)
    }

    /** 历史导航（后退/前进/刷新——合并减少函数数——detekt TooManyFunctions）。
     *  AD-081（2026-09-26 审计）：lateinit 守卫收敛 withTabManager。 */
    fun navigateHistory(action: HistoryAction) {
        withTabManager { tm ->
            val wv = tm.current()?.webView ?: return@withTabManager
            if (!SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(action).orFalse()) {
                _webViewAlert.value = alertText(R.string.history_unavailable)
            }
            // AD-064：历史导航后立即同步前进/后退可用性（缓存页导航等无网络
            // 事件的场景也准确）
            refresh()
        }
    }

    /** 设置/清除安全提示（null = 清除）。 */
    fun setWebViewAlert(message: String?) {
        _webViewAlert.value = message
    }

    /**
     * P2-1 修复（全面审计 2026-09-04）：清除页面错误面板。新导航开始时由
     * 装配点自动触发，重试 / 返回安全页按钮也走此入口。
     */
    fun clearPageError() {
        _pageError.value = null
    }

    /** P2-1 修复：错误面板「重试」——清错误状态后 reload 当前标签。 */
    fun retryCurrentPage() {
        clearPageError()
        navigateHistory(HistoryAction.RELOAD)
    }

    /** P2-1 修复：错误面板「返回安全页」——当前标签回到受信首页。
     *  AD-141（审计 2026-09-23 清单·A6 批）：`wv ?: return` 内联于实参
     *  表达式的中缀 return 与全文件守卫风格不一——随 withTabManager 收敛
     *  改写，不再存在内联 return。 */
    fun returnToSafeHome() {
        clearPageError()
        withTabManager { tm ->
            tm.current()?.webView?.let { wv ->
                SecureWebViewFactory.navigatorFor(wv)?.openTrustedHome()
            }
        }
    }

    /**
     * Compose 的明确批准操作。只允许当前活动标签的待审批请求恢复导航，防止标签切换后
     * 在错误 WebView 上消费授权；客户端仍会在恢复前调用 Rust 核心批准并消费。
     */
    fun approvePendingNavigationConfirmation(): Boolean {
        val pending = _pendingNavigationConfirmation.value ?: return false
        if (tabManager?.current()?.webView !== pending.webView) {
            _webViewAlert.value = alertText(R.string.confirm_switch_back)
            return false
        }
        _pendingNavigationConfirmation.value = null
        val approved =
            SecureWebViewFactory
                .navigatorFor(pending.webView)
                ?.approvePendingNavigation() == true
        if (!approved) _webViewAlert.value = alertText(R.string.confirm_invalid)
        return approved
    }

    /** 对话框关闭、返回键或拒绝按钮一律走此入口；失败不会恢复导航。 */
    fun rejectPendingNavigationConfirmation(): Boolean {
        val pending = _pendingNavigationConfirmation.value ?: return false
        _pendingNavigationConfirmation.value = null
        return SecureWebViewFactory.navigatorFor(pending.webView)?.rejectPendingNavigation() == true
    }

    /** 获取 TabManager 实例（供 WebContentArea 使用）。 */
    fun getTabManager(): TabManager? = tabManager

    /** P1-3 修复：渲染进程崩溃后原位重建 WebView 并重载原 URL（主线程异步执行）。 */
    private fun rebuildAfterRendererGone(deadWebView: WebView) {
        // P0-6 修复：优先用宿主 Activity context 创建 WebView——appContext
        // （无主题）创建的 WebView 一弹原生对话框即崩（token null）。
        val context = resolveRebuildContext() ?: return
        // AD-059（2026-09-24 审计）：裸 Handler → viewModelScope（生命周期感知）。
        viewModelScope.launch(Dispatchers.Main) {
            withTabManager { tm ->
                val index = tm.list().indexOfFirst { it.webView === deadWebView }
                if (index < 0) return@withTabManager
                val crashedUrl = tm.list()[index].url
                // AD-061（2026-09-24 审计）：销毁收敛 tearDown 单源。
                SecureWebViewFactory.tearDown(deadWebView)
                val fresh = createSecureWebView(context)
                tm.replaceWebView(index, fresh)
                val navigator = SecureWebViewFactory.navigatorFor(fresh)
                if (crashedUrl.isNotBlank() && crashedUrl != HOME_URL) {
                    navigator?.navigateExternal(crashedUrl)
                } else {
                    navigator?.openTrustedHome()
                }
                refresh()
                _webViewAlert.value = alertText(R.string.renderer_restored)
            }
        }
    }

    /**
     * P0-6 修复：崩溃重建 context 解析——优先宿主 Activity；拿不到（配置
     * 变更重建间隙 / 已退出 detach）回退 appContext 并 Log.w 留痕。
     */
    private fun resolveRebuildContext(): android.content.Context? {
        val activity = hostBindings.availableOrNull()
        if (activity != null) return activity
        android.util.Log.w("Aegis", "P0-6: 崩溃重建拿不到宿主 Activity，回退 appContext（原生对话框可能不可用）")
        return appContext
    }

    private fun createSecureWebView(context: android.content.Context): WebView = webViewEvents.create(context)

    // ---------------- WebViewEventAssembly.Host 接缝（AD-103；实现在
    // BrowserViewModelHost.kt——A7 批抽出使本文件回到改造红线 500 行内） ----------------

    private val hostImpl =
        BrowserViewModelHost(
            tabManagerOrNull = ::getTabManager,
            addressDraftActive = { addressDraftActive },
            mapDisplayAddress = ::displayAddress,
            onSubmitPageAddress = { _address.value = it },
            onSubmitPageError = { _pageError.value = it },
            onClearPageError = { this@BrowserViewModel.clearPageError() },
            onSubmitWebViewAlert = { _webViewAlert.value = it },
            onRefreshTabs = ::refresh,
            errorStrings = { pageErrorStringsOf(::alertText, ::alertText) },
        )

    /**
     * 装配对象（AD-103）。AD-196（审计 2026-09-23 清单·A7 批）：显式构造
     * 取代 lazy——装配点仅捕获回调，构造期初始化消除注释级时序约束
     * （create() 仍只在 init() 中被调用，时序语义不变）。
     */
    private val webViewEvents: WebViewEventAssembly =
        WebViewEventAssembly(
            broker = broker,
            host = hostImpl,
            onRendererGone = ::rebuildAfterRendererGone,
            onConfirmationRequested = ::registerPendingConfirmation,
            onConfirmationResolved = ::resolvePendingConfirmation,
        )

    /** 仅 ViewModel 保存发起 WebView 引用（PendingNavigationConfirmation 单写点）。
     *  AD-158 配套：internal 化供 JVM/Robolectric 单测注入待审批状态。 */
    internal fun registerPendingConfirmation(
        webView: WebView,
        request: ApprovalRequest,
    ) {
        _pendingNavigationConfirmation.value = PendingNavigationConfirmation(webView, request)
    }

    /** 待审批解除：仅当解除请求来自挂起请求自身（幂等防错标）。 */
    private fun resolvePendingConfirmation(webView: WebView) {
        if (_pendingNavigationConfirmation.value?.webView === webView) {
            _pendingNavigationConfirmation.value = null
        }
    }

    /** AD-046：提示文案经资源单源（init 后 appContext 必然可用）。 */
    private fun alertText(id: Int): String = appContext?.getString(id).orEmpty()

    private fun alertText(
        id: Int,
        arg: String,
    ): String = appContext?.getString(id, arg).orEmpty()
}

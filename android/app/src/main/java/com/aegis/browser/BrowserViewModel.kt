package com.aegis.browser

import android.webkit.WebView
import android.widget.Toast
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** AD-303（2026-10-02 审计）：地址栏外跳 scheme 分型集合（与 WebViewClient 同源）。 */
private val EXTERNAL_HANDLER_SCHEMES = com.aegis.webviewadapter.AegisWebViewClient.externalHandlerSchemes

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

        // AD-326（2026-10-02 审计）：会话持久化键/读写单源在 TabSessionState
        // （BrowserModels.kt）——此处别名保持既有引用形态稳定。
        const val STATE_TAB_URLS = TabSessionState.TAB_URLS

        const val STATE_ACTIVE_TAB_INDEX = TabSessionState.ACTIVE_TAB_INDEX

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

    // AD-260（2026-10-01 审计）：安全提示分型——一般提示（导航被拒/历史不可用
    // 等）单按钮「知道了」；版本检查提示经 [setWebViewVersionAlert] 登记
    // （双按钮「去更新/稍后」）。原 String? 单态使所有提示共用版本检查按钮。
    // 拆分批（2026-10-03）：安全提示 + 双确认流内聚到 BrowserViewModelConfirmations
    // （AD-103 host 接缝同款模式）——公开读与操作经委托保持签名不变（单测零改动）。
    private val confirmations =
        BrowserViewModelConfirmations(
            currentWebView = { currentTabManager?.current()?.webView },
            resolveText = { id -> appContext?.getString(id).orEmpty() },
            resolveTextWithArg = { id, arg -> appContext?.getString(id, arg).orEmpty() },
        )

    val webViewAlert: StateFlow<WebViewAlertNotice?> get() = confirmations.webViewAlert

    val pendingNavigationConfirmation: StateFlow<PendingNavigationConfirmation?>
        get() = confirmations.pendingNavigationConfirmation

    val pendingDownloadConfirmation: StateFlow<PendingDownloadConfirmation?>
        get() = confirmations.pendingDownloadConfirmation

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
            alertRes = { res -> confirmations.setSecurityNotice(res) },
        )

    // 拆分批（2026-10-03·第二块）：标签生命周期 + 崩溃重建内聚到
    // BrowserViewModelTabs（AD-103 host 接缝同款模式）——公开读与操作经
    // 委托保持签名不变（单测零改动）。tabManager 经 alias 保持文件内
    // 全部直用点形态不变（可空字段语义——AD-003 R8 口径随块迁控制器）。
    private val tabsController =
        BrowserViewModelTabs(
            createWebView = { webViewEvents.create(it) },
            rebuildContext = {
                hostBindings.availableOrNull() ?: appContext.also {
                    android.util.Log.w("Aegis", "P0-6: 崩溃重建拿不到宿主 Activity，回退 appContext（原生对话框可能不可用）")
                }
            },
            launchOnMain = { block -> viewModelScope.launch(Dispatchers.Main) { block() } },
            isDraftActive = { addressDraftActive },
            clearDraft = { addressDraftActive = false },
            setAddress = { _address.value = it },
            pageErrorWebView = { _pageError.value?.webView },
            clearPageError = { _pageError.value = null },
            confirmations = confirmations,
        )

    private val currentTabManager: TabManager? get() = tabsController.tabManagerOrNull()

    val tabs: StateFlow<List<Tab>> get() = tabsController.tabs

    val activeIndex: StateFlow<Int> get() = tabsController.activeIndex

    val canGoBack: StateFlow<Boolean> get() = tabsController.canGoBack

    val canGoForward: StateFlow<Boolean> get() = tabsController.canGoForward

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
    fun currentWebViewOrNull(): WebView? = currentTabManager?.current()?.webView

    /**
     * AD-149（审计 2026-09-23 清单·A6 批）：TabManager 守卫样板单源——
     * `if (!::tabManager.isInitialized) return` 此前散落 8+ 处，收敛为本
     * 收口；init 前调用静默忽略（对齐类内索引操作约定）。
     */
    private fun withTabManager(block: (TabManager) -> Unit) = tabsController.withTabManager(block)

    /**
     * 初始化 TabManager 并创建首个标签。
     *
     * AD-307（2026-10-02 审计）：标签 WebView 改 applicationContext 创建——持
     * Activity context 创建会在配置变更重建后泄漏旧 Activity（density/locale
     * 等未声明项）；崩溃重建路径不受影响（仍优先宿主 Activity context，P0-6）。
     * AD-326（2026-10-02 审计）：savedInstanceState 携带会话态（仅 https）时
     * 恢复标签——经 navigateExternal 安全链路重载，不新增特权入口。
     */
    fun init(
        context: android.content.Context,
        savedInstanceState: android.os.Bundle? = null,
    ) {
        appContext = context.applicationContext
        tabsController.init(context, savedInstanceState)
    }

    /** AD-326：会话态写出（MainActivity.onSaveInstanceState 调用）——单源在
     *  [TabSessionState]（tab.url 仅 https 外存；activeIndex 映射过滤后列表）。 */
    fun writeSessionState(outState: android.os.Bundle) = tabsController.writeSessionState(outState)

    /** 刷新状态（从 TabManager 同步到 StateFlow——单源在 tabsController）。 */
    fun refresh() = tabsController.refresh()

    /** 新建标签页（单源在 tabsController）。 */
    fun newTab(context: android.content.Context) = tabsController.newTab(context)

    /** 切换到指定标签（单源在 tabsController）。 */
    fun switchTo(index: Int) = tabsController.switchTo(index)

    /** 关闭指定标签（单源在 tabsController）。 */
    fun closeTab(index: Int) = tabsController.closeTab(index)

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
     *
     * AD-328 配套：[targetOverride] 供外链 intent 在草稿激活时以显式目标
     * 导航（不经地址栏字段中转——草稿不被覆写）。
     */
    private fun navigateWithDebounce(
        bypassDebounce: Boolean,
        targetOverride: String? = null,
    ) {
        val wv = currentTabManager?.current()?.webView
        if (wv == null ||
            (!bypassDebounce && !navigateDebounce.ok(confirmations.pendingNavigationConfirmation.value != null))
        ) {
            return
        }
        // AD-238（2026-09-26 审计）：地址栏停留首页占位（用户未编辑）时点
        // 「打开」——占位 aegis://home 不可导航，映射回 HOME_URL（等价刷新）。
        val target =
            targetOverride
                ?: if (_address.value == HOME_DISPLAY_URL) HOME_URL else _address.value
        // AD-111（2026-09-23 审计）：空输入无导航意图，静默 no-op。
        // AD-303（2026-10-02 审计·云端实证）：外跳 scheme 进归一链前拦截——
        // tel:10086 会被误判 host:port 归一成 https://tel:10086 白白导航；
        // 反馈不依赖 broker（scheme 集与 AD-304 同源）。两分支合一（detekt
        // ReturnCount≤2）。空输入/外跳都就地终止，不进归一链。
        val silentSkip = target.isBlank()
        val externalScheme = !silentSkip && target.substringBefore(':', "").lowercase() in EXTERNAL_HANDLER_SCHEMES
        if (silentSkip || externalScheme) {
            if (externalScheme) {
                appContext?.let { ctx ->
                    Toast.makeText(ctx, R.string.unsupported_link_scheme, Toast.LENGTH_SHORT).show()
                }
            }
            return
        }
        // 提交即清除草稿：后续 onPageStarted→onPageUrlObserved 正常同步地址栏
        addressDraftActive = false
        val navigated = SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(target).orFalse()
        if (!navigated &&
            // AD-216（2026-09-26 审计）：RequireConfirmation「待确认」与 Deny
            // 「被拒」共用 false 返回——确认对话框已挂起时不得再弹恐吓提示。
            confirmations.pendingNavigationConfirmation.value == null
        ) {
            confirmations.setSecurityNotice(R.string.nav_rejected)
        }
    }

    /**
     * P1-4 修复（全面审计批次4）：外链 intent 消费——经地址栏同一安全链路
     * （归一 + OriginPolicy + broker），非法 scheme 走既有拒绝反馈
     * （fail-closed），不新增特权入口。AD-048：外链绕过防抖。
     *
     * AD-328（2026-10-02 审计）：草稿激活时跳过地址栏覆写（后台到达的外链
     * 导航不得打断用户输入——与 refresh/onPageUrlObserved 草稿保护同口径）；
     * 导航本身照常发起（经显式目标，不经地址栏字段中转）。
     */
    fun openExternalUrl(url: String?) {
        if (url.isNullOrBlank()) return
        if (!addressDraftActive) {
            _address.value = url
        }
        navigateWithDebounce(bypassDebounce = true, targetOverride = url)
    }

    /** 历史导航（后退/前进/刷新——合并减少函数数——detekt TooManyFunctions）。
     *  AD-081（2026-09-26 审计）：lateinit 守卫收敛 withTabManager。 */
    fun navigateHistory(action: HistoryAction) {
        withTabManager { tm ->
            val wv = tm.current()?.webView ?: return@withTabManager
            if (SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(action).orFalse()) {
                // AD-266（2026-10-01 审计）：导航成功即清地址草稿——历史导航
                // （含返回/前进到已缓存页，无网络事件链路）后页面已变，地址栏
                // 不得停留旧草稿（与 navigateWithDebounce 提交路径同口径）。
                addressDraftActive = false
            } else {
                confirmations.setSecurityNotice(R.string.history_unavailable)
            }
            // AD-064：历史导航后立即同步前进/后退可用性（缓存页导航等无网络
            // 事件的场景也准确）
            refresh()
        }
    }

    /** 设置/清除一般安全提示（null = 清除；AD-260：单按钮「知道了」分型）。 */
    fun setWebViewAlert(message: String?) = confirmations.setWebViewAlert(message)

    /** AD-260：登记版本检查提示（双按钮「去更新/稍后」——与一般提示分型）。 */
    fun setWebViewVersionAlert(message: String) = confirmations.setWebViewVersionAlert(message)

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
    fun approvePendingNavigationConfirmation(): Boolean = confirmations.approvePendingNavigationConfirmation()

    /** 对话框关闭、返回键或拒绝按钮一律走此入口；失败不会恢复导航。 */
    fun rejectPendingNavigationConfirmation(): Boolean = confirmations.rejectPendingNavigationConfirmation()

    /** AD-331：下载确认「仍要下载」——续体单次调用（重复点击 no-op）。 */
    fun approvePendingDownload() = confirmations.approvePendingDownload()

    /** AD-331：下载确认拒绝/关闭——放弃待确认下载（fail-closed）。 */
    fun rejectPendingDownload() = confirmations.rejectPendingDownload()

    /** 获取 TabManager 实例（供 WebContentArea 使用）。 */
    fun getTabManager(): TabManager? = currentTabManager

    // ---------------- WebViewEventAssembly.Host 接缝（AD-103；实现在
    // BrowserViewModelHost.kt——A7 批抽出使本文件回到改造红线 500 行内） ----------------

    private val hostImpl =
        BrowserViewModelHost(
            tabManagerOrNull = ::getTabManager,
            addressDraftActive = { addressDraftActive },
            mapDisplayAddress = tabsController::displayAddress,
            onSubmitPageAddress = { _address.value = it },
            onSubmitPageError = { _pageError.value = it },
            onClearPageError = { this@BrowserViewModel.clearPageError() },
            onSubmitWebViewAlert = { message -> confirmations.setWebViewAlert(message) },
            onRefreshTabs = ::refresh,
            // AD-332 回归修复：宿主构造参数随 BrowserViewModelHost 属性改名
            // （errorStrings → resolveErrorStrings——消除与 override fun
            // errorStrings() 的同名遮蔽，AD-003 同型）。
            resolveErrorStrings = { pageErrorStringsOf(confirmations::alertText, confirmations::alertText) },
            // AD-331：二级下载确认登记（单槽状态——MainDialogs 渲染）
            onRequestDownloadConfirmation = confirmations::registerPendingDownload,
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
            onRendererGone = tabsController::rebuildAfterRendererGone,
            onConfirmationRequested = confirmations::registerPendingConfirmation,
            onConfirmationResolved = confirmations::resolvePendingConfirmation,
        )

    /** 仅 ViewModel 保存发起 WebView 引用（AD-158：internal 化供 JVM 单测注入）。 */
    internal fun registerPendingConfirmation(
        webView: WebView,
        request: ApprovalRequest,
    ) = confirmations.registerPendingConfirmation(webView, request)
}

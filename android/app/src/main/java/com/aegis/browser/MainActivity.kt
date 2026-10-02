package com.aegis.browser

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 主界面（薄壳，仅负责组装；多标签逻辑在 TabManager，标签栏在 TabBar/VerticalTabBar）。
 *
 * S4 变更（对比旧版单 WebView）：
 * - 每个标签持有独立 WebView（TabManager 管理），切换时显示/隐藏，
 *   保留各页面状态；
 * - 所有 WebView 经 SecureWebViewFactory 创建（安全配置统一）；
 * - onDestroy 统一释放全部 WebView。
 *
 * 落地 B：支持标签栏布局切换（[TabsPosition].TOP 顶部横排 | LEFT 左侧垂直），
 * 默认 TOP（与既有行为一致）；LEFT 走 VerticalTabBar。
 *
 * AD-101（审计 2026-09-23 清单·A6 批）：地址栏（AddressBarUi.kt）、页面内容区
 * （WebContentAreaUi.kt）与对话框（MainDialogs.kt——AD-183，本批）组件抽出
 * ——本文件只保留 Activity 生命周期、回调装配与布局编排。
 */
class MainActivity : ComponentActivity() {
    // 架构解耦（第 5 项）：broker 经工厂注入 ViewModel——Application 强转取
    // broker 收敛到这一个组合点（factory(application)），其余层不再强转。
    private val viewModel: BrowserViewModel by viewModels { BrowserViewModel.factory(application) }

    /**
     * AD-302（2026-10-02 审计）：外链频控状态机抽独立类（原时间戳字段内联于
     * onNewIntent，不可 JVM 单测）。AD-283 语义不变 + 修复：data=null 或
     * action≠VIEW 的 intent 不烧频控窗口（原实现判 intent.data 前推进时间戳
     * ——空 intent 也会打断面）。
     */
    private val externalIntentRateLimit = ExternalIntentRateLimit(EXTERNAL_INTENT_MIN_INTERVAL_MS)

    private companion object {
        /** AD-283：外链 intent 最小消费间隔（毫秒）。 */
        const val EXTERNAL_INTENT_MIN_INTERVAL_MS = 1_500L
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // edge-to-edge（targetSdk 36 在 Android 15+ 强制启用）：内容默认延伸进
        // 状态栏/导航栏挖空区——此前标签栏画在透明状态栏下面，系统时钟/电量
        // 与「新标签页 ×」文字叠印（真机回归 2026-09-02 实锤）。显式声明
        // 不适配 + 深色 chrome → 状态栏图标转浅色，根布局用 insets padding 让位。
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val insetsController = WindowCompat.getInsetsController(window, window.decorView)
        // AD-190（审计 2026-09-23 清单·A7 批）：图标明暗由 chrome 底色单源派生
        // ——原 `isAppearanceLightStatusBars = false` 硬编码「永远浅色图标」，
        // 与底色无派生关系（底色改浅色系时图标不可见）。底色取 colors.xml
        // 单源（chrome_background，与 Compose 页面区背景同一资源）。
        insetsController.isAppearanceLightStatusBars =
            !statusBarUsesLightIcons(ContextCompat.getColor(this, R.color.chrome_background))
        // A1：System WebView 版本检查（CVE-2026-12438/11295 防御——
        // 过旧则提示更新，不阻塞浏览）
        // AD-058（2026-09-24 审计）：getPackageInfo 是 PackageManager 查询
        // （可能触发 binder IPC）——移出主线程，协程内检查、结果回主线程提示。
        lifecycleScope.launch(Dispatchers.Default) {
            // AD-239（2026-09-26 审计）：检查经 ViewModel 存续层去重——未声明
            // configChanges 的变更触发 Activity 重建后不得再次弹提示。
            viewModel.checkWebViewVersionOnce { message ->
                // AD-260（2026-10-01 审计）：版本检查提示走 VERSION_CHECK 分型
                // （双按钮「去更新/稍后」）——与一般安全提示（单按钮）分型渲染。
                lifecycleScope.launch(Dispatchers.Main) { viewModel.setWebViewVersionAlert(message) }
            }
        }
        // AD-197（审计 2026-09-23 清单·A7 批）：冷启动装配时序固化（次序即
        // 契约，不得重排）——
        //   ① init：TabManager 必须先就位（openExternalUrl 的导航链路依赖
        //      当前标签 WebView；init 内可空字段判空 `if (tabManager != null)
        //      return` 幂等——AD-003 R8 回归起 lateinit 判空已改可空字段口径，
        //      配置变更重建时安全直通）；
        //   ② attachActivity：宿主弱引用随后注入（P0-6 崩溃重建需要主题化
        //      Activity context，晚于 init 只损失「init 当刻即崩溃」的极端窗口）；
        //   ③ openExternalUrl：最后消费冷启动外链——此时安全导航链路（策略
        //      决策 + 防抖 + 错误上抛）才具备完整前提，外链不会被静默丢弃。
        // AD-326（2026-10-02 审计）：init 透传 savedInstanceState——进程被杀
        // 重建时恢复标签会话（tab.url 列表 + activeIndex，经安全导航链重载）。
        viewModel.init(this, savedInstanceState)
        viewModel.attachActivity(this)
        viewModel.openExternalUrl(intent?.data?.toString())

        // 返回事件统一接管（BUG-013）：targetSdk 36 起系统默认经
        // OnBackInvokedCallback 分发返回（手势导航的边缘滑动与
        // KEYCODE_BACK 都不再经过 onKeyDown）。OnBackPressedCallback 由
        // androidx 桥接两种分发路径；无历史时保留原退出语义。
        onBackPressedDispatcher.addCallback(this, BackPressHandler())

        setContent {
            AegisTheme {
                MainBrowserContent()
            }
        }
    }

    /**
     * AD-183（审计 2026-09-23 清单·A7 批）：主内容装配抽组合函数——onCreate
     * 只负责生命周期与 setContent 入口；状态收集、对话框状态机（AD-151）与
     * 双布局编排收敛在此（Compose 上下文，可读性优先）。
     */
    @Suppress("FunctionNaming")
    @Composable
    private fun MainBrowserContent() {
        // AD-038：collectAsState → collectAsStateWithLifecycle（后台不再
        // 空转收集，回到前台自动恢复——省电且避免后台重组）
        val tabs by viewModel.tabs.collectAsStateWithLifecycle()
        val activeIndex by viewModel.activeIndex.collectAsStateWithLifecycle()
        val address by viewModel.address.collectAsStateWithLifecycle()
        val tabsPosition by viewModel.tabsPosition.collectAsStateWithLifecycle()
        val webViewAlert by viewModel.webViewAlert.collectAsStateWithLifecycle()
        val pendingConfirmation by viewModel.pendingNavigationConfirmation.collectAsStateWithLifecycle()
        val pageError by viewModel.pageError.collectAsStateWithLifecycle()
        val readerContent by viewModel.reader.content.collectAsStateWithLifecycle()
        // AD-331：待确认下载（二级——仅查询参数命中危险扩展）
        val pendingDownload by viewModel.pendingDownloadConfirmation.collectAsStateWithLifecycle()
        // AD-064：前进/后退可用性
        val canGoBack by viewModel.canGoBack.collectAsStateWithLifecycle()
        val canGoForward by viewModel.canGoForward.collectAsStateWithLifecycle()

        // AD-151（审计 2026-09-23 清单·A7 批）：对话框单槽状态机——同一时刻
        // 至多呈现一个对话框（优先级见 MainDialogs.resolveActiveDialog）。
        MainDialogHost(
            pendingConfirmation = pendingConfirmation,
            pendingDownload = pendingDownload,
            webViewAlert = webViewAlert,
            readerContent = readerContent,
            onApprove = { viewModel.approvePendingNavigationConfirmation() },
            onReject = { viewModel.rejectPendingNavigationConfirmation() },
            // AD-331：二级下载确认（批准继续入队/拒绝放弃）
            onApproveDownload = { viewModel.approvePendingDownload() },
            onRejectDownload = { viewModel.rejectPendingDownload() },
            onDismissAlert = { viewModel.setWebViewAlert(null) },
            onGoUpdate = {
                viewModel.setWebViewAlert(null)
                // AD-204（审计 2026-09-23 清单·A7 批）：去更新失败降级
                // ——无 Play Store/无浏览器时跳转静默失败，回填提示。
                if (!WebViewVersionCheck.openUpdate(this@MainActivity)) {
                    viewModel.setWebViewAlert(getString(R.string.update_open_failed))
                }
            },
            onDismissReader = { viewModel.reader.dismissReader() },
        )

        MainBrowserChromeLayout(
            tabs = tabs,
            activeIndex = activeIndex,
            address = address,
            tabsPosition = tabsPosition,
            pageError = pageError,
            canGoBack = canGoBack,
            canGoForward = canGoForward,
        )
    }

    /**
     * AD-183：chrome 双布局编排组合函数（top 横排 / left 垂直）——状态由
     * [MainBrowserContent] 收集后传入；交互经 ViewModel 意图入口上抛。
     */
    @Suppress("FunctionNaming", "LongParameterList")
    @Composable
    private fun MainBrowserChromeLayout(
        tabs: List<Tab>,
        activeIndex: Int,
        address: String,
        tabsPosition: TabsPosition,
        pageError: PageError?,
        canGoBack: Boolean,
        canGoForward: Boolean,
    ) {
        // AD-153（审计 2026-09-23 清单·A7 批）：根布局衬底经语义色板取色
        val chrome = LocalAegisChromeColors.current
        Column(
            modifier =
                Modifier
                    .fillMaxSize()
                    .background(chrome.chromeBackground)
                    .statusBarsPadding()
                    .navigationBarsPadding(),
        ) {
            // —— 标签栏（top 横排 / left 垂直，按布局切换）——
            if (tabsPosition == TabsPosition.LEFT) {
                Row(modifier = Modifier.fillMaxSize()) {
                    VerticalTabBar(
                        tabs = tabs,
                        activeIndex = activeIndex,
                        onSelect = { viewModel.switchTo(it) },
                        onClose = { viewModel.closeTab(it) },
                        onNewTab = { viewModel.newTab(this@MainActivity) },
                    )
                    // AD-251（2026-09-26 审计）：left 分支同样含地址栏（布局
                    // 切换后用户不失去地址栏）；内容区占剩余宽度。
                    Column(modifier = Modifier.weight(1f)) {
                        AddressAndContent(
                            address = address,
                            activeIndex = activeIndex,
                            canGoBack = canGoBack,
                            canGoForward = canGoForward,
                            pageError = pageError,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            } else {
                TabBar(
                    tabs = tabs,
                    activeIndex = activeIndex,
                    onSelect = { viewModel.switchTo(it) },
                    onClose = { viewModel.closeTab(it) },
                    onNewTab = { viewModel.newTab(this@MainActivity) },
                )
                AddressAndContent(
                    address = address,
                    activeIndex = activeIndex,
                    canGoBack = canGoBack,
                    canGoForward = canGoForward,
                    pageError = pageError,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }

    /**
     * AD-183：地址栏 + 页面内容区装配（两种布局共用同一组装——此前在
     * top/left 分支各写一份）。
     *
     * @Suppress 与 AddressBarRow 同口径：状态/回调装配点参数多系设计使然。
     */
    @Suppress("FunctionNaming", "LongParameterList")
    @Composable
    private fun AddressAndContent(
        address: String,
        activeIndex: Int,
        canGoBack: Boolean,
        canGoForward: Boolean,
        pageError: PageError?,
        modifier: Modifier,
    ) {
        AddressBarRow(
            address = address,
            canGoBack = canGoBack,
            canGoForward = canGoForward,
            onAddressChange = { viewModel.updateAddress(it) },
            onOpen = { viewModel.navigateToAddress() },
            onBack = { viewModel.navigateHistory(HistoryAction.BACK) },
            onForward = { viewModel.navigateHistory(HistoryAction.FORWARD) },
            onReload = { viewModel.navigateHistory(HistoryAction.RELOAD) },
            onReader = { viewModel.reader.toggleReaderMode() },
            onTranslate = { viewModel.reader.translateCurrentPage() },
            onToggleLayout = { viewModel.toggleTabsPosition() },
        )
        WebContentArea(
            tabManager = requireNotNull(viewModel.getTabManager()),
            activeIndex = activeIndex,
            pageError = pageError,
            onRetry = { viewModel.retryCurrentPage() },
            onBackToSafePage = { viewModel.returnToSafeHome() },
            modifier = modifier,
        )
    }

    /**
     * 返回键处理器（BUG-013）。
     *
     * AD-140（审计 2026-09-23 清单·A6 批）：降级 finish——原实现 wv==null 时
     * 走 else-finish，但 navigatorFor(wv) 缺失（WebView 已注销的边界）时
     * `?.navigateHistory` 静默 no-op：用户按返回毫无反馈。收敛为「消费历史
     * 成功才留驻，否则一律降级 finish」，返回键语义全路径闭合。
     */
    private inner class BackPressHandler : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            val wv = viewModel.currentWebViewOrNull()
            val consumed =
                wv != null &&
                    wv.canGoBack() &&
                    SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(HistoryAction.BACK) == true
            if (!consumed) finish()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // AD-240（2026-09-26 审计）：更新宿主 Intent——不 setIntent 则后续
        // getIntent() 仍指旧 Intent（launchMode 复用路径的 intent 消费语义）。
        setIntent(intent)
        // AD-283（2026-10-01 审计）：外链消费频控——openExternalUrl 经
        // bypassDebounce 绕过防抖，第三方应用高频发 VIEW intent 可持续打断
        // 浏览（页面被顶替）。窗口期内（[EXTERNAL_INTENT_MIN_INTERVAL_MS]）
        // 的重复 intent 静默丢弃（显式用户外链不受影响——单次意图本就间隔
        // 远大于窗口）。
        // AD-302（2026-10-02 审计）：频控窗口只被「可消费」的 intent 烧
        // ——data=null 或 action≠VIEW 的 intent 不进频控判定（原实现判 data
        // 前推进时间戳，空 intent 也打断面）。
        val externalUrl = intent.data?.toString()
        val consumable = !externalUrl.isNullOrBlank() && intent.action == Intent.ACTION_VIEW
        if (consumable &&
            !externalIntentRateLimit.tryAcquire(android.os.SystemClock.elapsedRealtime(), consumable)
        ) {
            android.util.Log.w("Aegis", "外链 VIEW intent 超频被丢弃（AD-283 频控）")
            return
        }
        // P1-4 修复（全面审计批次4）：热启动外链消费——launchMode 调整或
        // singleTop 复用时 VIEW intent 经此分发；与 onCreate 冷启动路径
        // 同走 openExternalUrl 安全链路。
        viewModel.openExternalUrl(externalUrl)
    }

    /**
     * AD-326（2026-10-02 审计）：标签会话持久化——tab.url 列表 + activeIndex
     * （仅 https）写入 outState；init 检测 savedInstanceState 恢复。配置
     * 变更重建（configChanges 已声明项之外的变更）与进程被杀同走本路径。
     */
    override fun onSaveInstanceState(outState: android.os.Bundle) {
        super.onSaveInstanceState(outState)
        viewModel.writeSessionState(outState)
    }

    override fun onDestroy() {
        // P0-5 修复（全面审计 2026-09-04）：仅真正退出（isFinishing）才执行
        // 销毁。density/字号/locale/折叠屏等未在 configChanges 声明的变更会
        // 触发 Activity 重建而 ViewModel 存活（isChangingConfigurations）——
        // 此前无条件 suspendAll + tearDown(destroy WebView) 后 init() 早退
        // 不重建，全部标签持有已销毁 WebView（整窗白屏/崩溃）；重建场景
        // WebViews 必须保留供新 Activity 重新挂载。
        if (isFinishing) {
            // Activity 真正退出是确认 UI 的退出边界；任何待审批导航均须先撤销，不留可恢复能力。
            viewModel.rejectPendingNavigationConfirmation()
            // 释放全部 WebView 持有的 Chromium 资源（统一销毁序列单源）。
            // AD-072（2026-09-26 审计）：不再先 suspendAll——它只 pause 实例，
            // 紧随的 tearDown 全量 destroy 使 pause 全部冗余（后台化挂起由
            // onPause 的 suspendAll 承担，销毁路径不重复）。
            viewModel.getTabManager()?.let { tm ->
                tm.list().forEach { tab -> SecureWebViewFactory.tearDown(tab.webView) }
            }
            // P0-5 修复：解除宿主引用（弱引用，不阻止 Activity 回收）。
            viewModel.detachActivity()
        }
        super.onDestroy()
    }

    override fun onPause() {
        // 应用转后台或进入系统遮罩时没有持续可见的明确同意；恢复后必须重新请求审批。
        viewModel.rejectPendingNavigationConfirmation()
        // AD-006：后台即全局暂停页面 JS 定时器并挂起全部标签（隐私+电量）；
        // 回前台由 onResume 对称恢复当前标签
        viewModel.getTabManager()?.suspendAll()
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        // AD-006 对称恢复：resumeTimers + 恢复当前标签（后台标签保持挂起）
        viewModel.getTabManager()?.resumeOnForeground()
    }
}

/**
 * AD-302（2026-10-02 审计）：外链 VIEW intent 消费频控状态机（纯 Kotlin——
 * JVM 可测）。AD-283 语义：窗口期内的重复消费静默丢弃；AD-302 修复：
 * 非可消费 intent（data=null / action≠VIEW）不烧窗口——此前时间戳在判
 * data 前推进，空 intent 也会把后续真实外链挡在窗口外。
 *
 * 单线程约束：仅主线程（onNewIntent）调用，与 BrowserViewModel 草稿标记
 * 同口径（无原子类型加重语义）。
 */
internal class ExternalIntentRateLimit(
    private val minIntervalMs: Long,
) {
    private var lastConsumedAt = 0L

    /**
     * 尝试获取消费资格。[hasConsumableIntent]=false 恒 false 且不推进（不烧窗口）；
     * 冷启动（lastConsumedAt=0）首个可消费 intent 豁免窗口；窗口期内重复消费 false。
     */
    fun tryAcquire(
        now: Long,
        hasConsumableIntent: Boolean,
    ): Boolean {
        // AD-302 冷启动豁免（锚点 0=未曾消费）——detekt ReturnCount 重构曾丢失该豁免（云端实证）。
        val acquirable = hasConsumableIntent && (lastConsumedAt == 0L || now - lastConsumedAt >= minIntervalMs)
        if (acquirable) lastConsumedAt = now
        return acquirable
    }
}

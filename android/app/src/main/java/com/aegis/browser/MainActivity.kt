package com.aegis.browser

import android.content.Intent
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.WebView
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
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
 * 落地 B：支持标签栏布局切换（tabsPosition = "top" 顶部横排 | "left" 左侧垂直），
 * 默认 top（与既有行为一致）；left 走 VerticalTabBar（按分组/工作区渲染）。
 */
class MainActivity : ComponentActivity() {
    // 架构解耦（第 5 项）：broker 经工厂注入 ViewModel——Application 强转取
    // broker 收敛到这一个组合点（factory(application)），其余层不再强转。
    private val viewModel: BrowserViewModel by viewModels { BrowserViewModel.factory(application) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // edge-to-edge（targetSdk 36 在 Android 15+ 强制启用）：内容默认延伸进
        // 状态栏/导航栏挖空区——此前标签栏画在透明状态栏下面，系统时钟/电量
        // 与「新标签页 ×」文字叠印（真机回归 2026-09-02 实锤）。显式声明
        // 不适配 + 深色 chrome → 状态栏图标转浅色，根布局用 insets padding 让位。
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val insetsController = WindowCompat.getInsetsController(window, window.decorView)
        insetsController.isAppearanceLightStatusBars = false
        // A1：System WebView 版本检查（CVE-2026-12438/11295 防御——
        // 过旧则提示更新，不阻塞浏览）
        // AD-058（2026-09-24 审计）：getPackageInfo 是 PackageManager 查询
        // （可能触发 binder IPC）——移出主线程，协程内检查、结果回主线程提示。
        lifecycleScope.launch(Dispatchers.Default) {
            WebViewVersionCheck.checkAndPrompt(this@MainActivity) { message ->
                lifecycleScope.launch(Dispatchers.Main) { viewModel.setWebViewAlert(message) }
            }
        }
        // 初始化 ViewModel（TabManager + 首个标签）
        viewModel.init(this)
        // P0-5 修复（全面审计 2026-09-04）：向 ViewModel 注入宿主引用（弱引用
        // 持有）——P0-6 崩溃重建需用 Activity context 创建 WebView；onDestroy
        // 且 isFinishing 时 detach。
        viewModel.attachActivity(this)
        // P1-4 修复（全面审计批次4）：冷启动外链消费——VIEW intent 的 URL
        // 经安全导航链路加载（此前声明了 intent-filter 却静默丢弃 URL）
        viewModel.openExternalUrl(intent?.data?.toString())

        // 返回事件统一接管（BUG-013）：targetSdk 36 起系统默认经
        // OnBackInvokedCallback 分发返回（手势导航的边缘滑动与
        // KEYCODE_BACK 都不再经过 onKeyDown——此前 onKeyDown 实现
        // 在手势导航设备上从未生效，边缘滑动直接退出应用）。
        // OnBackPressedCallback 由 androidx 桥接两种分发路径；
        // 无历史时保留原退出语义。
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    val wv = viewModel.currentWebViewOrNull()
                    if (wv != null && wv.canGoBack()) {
                        SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(HistoryAction.BACK)
                    } else {
                        finish()
                    }
                }
            },
        )

        setContent {
            AegisTheme {
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
                // AD-064：前进/后退可用性
                val canGoBack by viewModel.canGoBack.collectAsStateWithLifecycle()
                val canGoForward by viewModel.canGoForward.collectAsStateWithLifecycle()

                // 阅读模式：提取到的正文以对话框渲染（INV-04：状态来自 ViewModel）
                readerContent?.let { content ->
                    AlertDialog(
                        onDismissRequest = { viewModel.reader.dismissReader() },
                        title = { Text(content.title) },
                        text = {
                            Column {
                                Text(
                                    text = content.text,
                                    modifier =
                                        Modifier
                                            .fillMaxWidth()
                                            .heightIn(max = 420.dp)
                                            .verticalScroll(rememberScrollState()),
                                )
                            }
                        },
                        confirmButton = {
                            TextButton(onClick = { viewModel.reader.dismissReader() }) {
                                Text(stringResource(R.string.dialog_close))
                            }
                        },
                    )
                }

                // A1：版本过旧 → 安全提示对话框（CVE-2026-12438/11295 防御）
                webViewAlert?.let { msg ->
                    AlertDialog(
                        onDismissRequest = { viewModel.setWebViewAlert(null) },
                        title = { Text(stringResource(R.string.alert_title)) },
                        text = { Text(msg) },
                        confirmButton = {
                            TextButton(
                                onClick = {
                                    viewModel.setWebViewAlert(null)
                                    WebViewVersionCheck.openUpdate(this@MainActivity)
                                },
                            ) { Text(stringResource(R.string.alert_go_update)) }
                        },
                        dismissButton = {
                            TextButton(onClick = { viewModel.setWebViewAlert(null) }) {
                                Text(stringResource(R.string.alert_later))
                            }
                        },
                    )
                }

                // 受信 Compose chrome 审批层：远程页面没有该回调或授权对象；默认关闭即拒绝。
                pendingConfirmation?.let { pending ->
                    AlertDialog(
                        onDismissRequest = { viewModel.rejectPendingNavigationConfirmation() },
                        title = { Text(stringResource(R.string.confirm_title)) },
                        text = {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(stringResource(R.string.confirm_origin, pending.request.origin))
                                Text(stringResource(R.string.confirm_path, pending.request.path))
                                Text(stringResource(R.string.confirm_scope, pending.request.scope))
                                Text(stringResource(R.string.confirm_expires, pending.request.expiresAt.toString()))
                            }
                        },
                        confirmButton = {
                            TextButton(onClick = { viewModel.approvePendingNavigationConfirmation() }) {
                                Text(stringResource(R.string.confirm_approve))
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = { viewModel.rejectPendingNavigationConfirmation() }) {
                                Text(stringResource(R.string.confirm_reject))
                            }
                        },
                    )
                }

                Column(
                    modifier =
                        Modifier
                            .fillMaxSize()
                            .background(ChromeBackground)
                            .statusBarsPadding()
                            .navigationBarsPadding(),
                ) {
                    // —— 标签栏（top 横排 / left 垂直，按布局切换）——
                    if (tabsPosition == "left") {
                        Row(modifier = Modifier.fillMaxSize()) {
                            VerticalTabBar(
                                tabs = tabs,
                                activeIndex = activeIndex,
                                onSelect = { viewModel.switchTo(it) },
                                onClose = { viewModel.closeTab(it) },
                                onNewTab = { viewModel.newTab(this@MainActivity) },
                            )
                            WebContentArea(
                                tabManager = requireNotNull(viewModel.getTabManager()),
                                pageError = pageError,
                                onRetry = { viewModel.retryCurrentPage() },
                                onBackToSafePage = { viewModel.returnToSafeHome() },
                                modifier = Modifier.weight(1f),
                            )
                        }
                    } else {
                        TabBar(
                            tabs = tabs,
                            activeIndex = activeIndex,
                            onSelect = { viewModel.switchTo(it) },
                            onClose = { viewModel.closeTab(it) },
                            onNewTab = { viewModel.newTab(this@MainActivity) },
                        )
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
                        )
                        WebContentArea(
                            tabManager = requireNotNull(viewModel.getTabManager()),
                            pageError = pageError,
                            onRetry = { viewModel.retryCurrentPage() },
                            onBackToSafePage = { viewModel.returnToSafeHome() },
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }
        }
    }

    /**
     * 地址栏 + 导航按钮（纯浏览态）。
     *
     * 2026-09-02 视觉重构：两行大按钮改为单行——玻璃圆钮（后退/前进/刷新/阅读/翻译）
     * + 深色玻璃胶囊地址栏；「打开」并入地址栏尾部按键与 IME「搜索」动作，
     * 不再占独立按钮位。贪吃蛇已迁移至首页 start.html（BUG-014——单源双端一致）。
     *
     * AD-064：后退/前进按历史可用性禁用（无历史时灰显且不可点）。
     *
     * Suppress 与 ChromeIconButton 同口径：Composable PascalCase 命名 +
     * 回调装配点参数多（AD-064 新增 canGoBack/canGoForward 后触发阈值）。
     */
    @Suppress("FunctionNaming", "LongParameterList")
    @Composable
    private fun AddressBarRow(
        address: String,
        canGoBack: Boolean,
        canGoForward: Boolean,
        onAddressChange: (String) -> Unit,
        onOpen: () -> Unit,
        onBack: () -> Unit,
        onForward: () -> Unit,
        onReload: () -> Unit,
        onReader: () -> Unit,
        onTranslate: () -> Unit,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ChromeIconButton(stringResource(R.string.cd_back), "←", canGoBack, onBack)
            ChromeIconButton(stringResource(R.string.cd_forward), "→", canGoForward, onForward)
            ChromeIconButton(stringResource(R.string.cd_reload), "⟳", true, onReload)
            OutlinedTextField(
                value = address,
                onValueChange = onAddressChange,
                modifier = Modifier.weight(1f),
                singleLine = true,
                placeholder = { Text(stringResource(R.string.address_placeholder), color = TextSecondary) },
                shape = CircleShape,
                colors =
                    OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = FieldBorderFocused,
                        unfocusedBorderColor = FieldBorderIdle,
                        focusedContainerColor = FieldBackground,
                        unfocusedContainerColor = FieldBackground,
                        cursorColor = Color.White,
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                    ),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { onOpen() }),
                trailingIcon = {
                    Text(
                        text = stringResource(R.string.address_open),
                        color = TextSecondary,
                        style = MaterialTheme.typography.labelSmall,
                        modifier =
                            Modifier
                                .padding(end = 6.dp)
                                .clickable(onClick = onOpen),
                    )
                },
            )
            ChromeIconButton(stringResource(R.string.cd_reader), "阅", true, onReader)
            ChromeIconButton(stringResource(R.string.cd_translate), "译", true, onTranslate)
        }
    }

    /**
     * 玻璃圆钮：工具栏图标按钮（半透明白圆形 + 居中字符图标）。
     *
     * AD-042（2026-09-24 审计）：补 [contentDescription] 语义（TalkBack 读出
     * 按钮用途——原纯字形「←/→/⟳/阅/译」无障碍不可用）；[enabled] 为 false
     * 时灰显且不可点（AD-064）。
     *
     * Composable 命名按 UI 惯例 PascalCase（与 [TabChipCore] 同口径）。
     */
    @Suppress("FunctionNaming")
    @Composable
    private fun ChromeIconButton(
        contentDescription: String,
        glyph: String,
        enabled: Boolean,
        onClick: () -> Unit,
    ) {
        val semanticsModifier =
            if (enabled) {
                Modifier.semantics { this.contentDescription = contentDescription }
            } else {
                Modifier
            }
        Surface(
            onClick = onClick,
            enabled = enabled,
            shape = CircleShape,
            color = ButtonOverlay,
            modifier =
                semanticsModifier
                    .alpha(if (enabled) 1f else DISABLED_BUTTON_ALPHA)
                    .size(38.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(text = glyph, color = Color.White, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }

    /** AD-064：禁用按钮灰显透明度（detekt MagicNumber 提取常量）。 */
    private companion object {
        const val DISABLED_BUTTON_ALPHA = 0.4f
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // P1-4 修复（全面审计批次4）：热启动外链消费——launchMode 调整或
        // singleTop 复用时 VIEW intent 经此分发；与 onCreate 冷启动路径
        // 同走 openExternalUrl 安全链路。
        viewModel.openExternalUrl(intent?.data?.toString())
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
            // 释放全部 WebView 持有的 Chromium 资源（统一销毁序列单源）
            viewModel.getTabManager()?.let { tm ->
                tm.suspendAll()
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
 * 页面容器：显示当前标签的 WebView（两种布局共用）。
 *
 * P2-1 修复（全面审计 2026-09-04）：错误状态非空时在内容区上方渲染
 * [PageErrorPanel]（原实现 SSL/加载错误静默白屏，无任何反馈）。
 */
@Suppress("FunctionNaming")
@Composable
private fun WebContentArea(
    tabManager: TabManager,
    pageError: PageError?,
    onRetry: () -> Unit,
    onBackToSafePage: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { FrameLayout(it) },
            update = { container ->
                val current = tabManager.current()
                if (current == null) return@AndroidView
                val wv = current.webView
                if (container.indexOfChild(wv) < 0) {
                    container.removeAllViews()
                    (wv.parent as? ViewGroup)?.removeView(wv)
                    container.addView(wv)
                }
            },
        )
        pageError?.let { error ->
            PageErrorPanel(
                error = error,
                onRetry = onRetry,
                onBackToSafePage = onBackToSafePage,
            )
        }
    }
}

/**
 * P2-1 修复（全面审计 2026-09-04）：页面错误面板——半透明遮罩盖住 WebView
 * 内容区。「重试」reload 当前标签；「返回安全页」回到受信首页。
 */
@Suppress("FunctionNaming")
@Composable
private fun PageErrorPanel(
    error: PageError,
    onRetry: () -> Unit,
    onBackToSafePage: () -> Unit,
) {
    Box(
        modifier =
            Modifier
                .fillMaxSize()
                .background(ErrorOverlayBackground)
                .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = stringResource(if (error.isSsl) R.string.error_ssl_title else R.string.error_title),
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = error.description,
                color = TextSecondary,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
            )
            Text(
                text = error.url,
                color = TextSecondary,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
                maxLines = 2,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Surface(onClick = onRetry, shape = CircleShape, color = ButtonOverlay) {
                    Text(
                        text = stringResource(R.string.error_retry),
                        color = Color.White,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(horizontal = 22.dp, vertical = 10.dp),
                    )
                }
                Surface(onClick = onBackToSafePage, shape = CircleShape, color = ButtonOverlay) {
                    Text(
                        text = stringResource(R.string.error_back_safe),
                        color = Color.White,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(horizontal = 22.dp, vertical = 10.dp),
                    )
                }
            }
        }
    }
}

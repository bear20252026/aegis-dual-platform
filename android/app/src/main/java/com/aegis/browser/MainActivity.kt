package com.aegis.browser

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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat

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
    private val viewModel: BrowserViewModel by viewModels()

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
        WebViewVersionCheck.checkAndPrompt(this) { viewModel.setWebViewAlert(it) }
        // 初始化 ViewModel（TabManager + 首个标签）
        viewModel.init(this)

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
                val tabs by viewModel.tabs.collectAsState()
                val activeIndex by viewModel.activeIndex.collectAsState()
                val address by viewModel.address.collectAsState()
                val tabsPosition by viewModel.tabsPosition.collectAsState()
                val webViewAlert by viewModel.webViewAlert.collectAsState()
                val pendingConfirmation by viewModel.pendingNavigationConfirmation.collectAsState()
                val readerContent by viewModel.reader.content.collectAsState()

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
                            TextButton(onClick = { viewModel.reader.dismissReader() }) { Text("关闭") }
                        },
                    )
                }

                // A1：版本过旧 → 安全提示对话框（CVE-2026-12438/11295 防御）
                webViewAlert?.let { msg ->
                    AlertDialog(
                        onDismissRequest = { viewModel.setWebViewAlert(null) },
                        title = { Text("安全提示") },
                        text = { Text(msg) },
                        confirmButton = {
                            TextButton(
                                onClick = {
                                    viewModel.setWebViewAlert(null)
                                    WebViewVersionCheck.openUpdate(this@MainActivity)
                                },
                            ) { Text("去更新") }
                        },
                        dismissButton = {
                            TextButton(onClick = { viewModel.setWebViewAlert(null) }) { Text("稍后") }
                        },
                    )
                }

                // 受信 Compose chrome 审批层：远程页面没有该回调或授权对象；默认关闭即拒绝。
                pendingConfirmation?.let { pending ->
                    AlertDialog(
                        onDismissRequest = { viewModel.rejectPendingNavigationConfirmation() },
                        title = { Text("需要确认的导航") },
                        text = {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("来源：${pending.request.origin}")
                                Text("路径与查询：${pending.request.path}")
                                Text("权限范围：${pending.request.scope}")
                                Text("此请求将在 ${pending.request.expiresAt} 过期。")
                            }
                        },
                        confirmButton = {
                            TextButton(onClick = { viewModel.approvePendingNavigationConfirmation() }) {
                                Text("批准并继续")
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = { viewModel.rejectPendingNavigationConfirmation() }) {
                                Text("拒绝")
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
                            WebContentArea(tabManager = viewModel.getTabManager()!!, modifier = Modifier.weight(1f))
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
                            onAddressChange = { viewModel.updateAddress(it) },
                            onOpen = { viewModel.navigateToAddress() },
                            onBack = { viewModel.navigateHistory(HistoryAction.BACK) },
                            onForward = { viewModel.navigateHistory(HistoryAction.FORWARD) },
                            onReload = { viewModel.navigateHistory(HistoryAction.RELOAD) },
                            onReader = { viewModel.reader.toggleReaderMode() },
                            onTranslate = { viewModel.reader.translateCurrentPage() },
                        )
                        WebContentArea(tabManager = viewModel.getTabManager()!!, modifier = Modifier.weight(1f))
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
     */
    @Composable
    private fun AddressBarRow(
        address: String,
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
            ChromeIconButton("←", onBack)
            ChromeIconButton("→", onForward)
            ChromeIconButton("⟳", onReload)
            OutlinedTextField(
                value = address,
                onValueChange = onAddressChange,
                modifier = Modifier.weight(1f),
                singleLine = true,
                placeholder = { Text("搜索或输入网址", color = TextSecondary) },
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
                        text = "打开",
                        color = TextSecondary,
                        style = MaterialTheme.typography.labelSmall,
                        modifier =
                            Modifier
                                .padding(end = 6.dp)
                                .clickable(onClick = onOpen),
                    )
                },
            )
            ChromeIconButton("阅", onReader)
            ChromeIconButton("译", onTranslate)
        }
    }

    /**
     * 玻璃圆钮：工具栏图标按钮（半透明白圆形 + 居中字符图标）。
     *
     * Composable 命名按 UI 惯例 PascalCase（与 [TabChipCore] 同口径）。
     */
    @Suppress("FunctionNaming")
    @Composable
    private fun ChromeIconButton(
        glyph: String,
        onClick: () -> Unit,
    ) {
        Surface(
            onClick = onClick,
            shape = CircleShape,
            color = ButtonOverlay,
            modifier = Modifier.size(38.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(text = glyph, color = Color.White, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }

    override fun onDestroy() {
        // Activity 销毁是确认 UI 的退出边界；任何待审批导航均须先撤销，不留可恢复能力。
        viewModel.rejectPendingNavigationConfirmation()
        // 释放全部 WebView 持有的 Chromium 资源（统一销毁序列单源）
        viewModel.getTabManager()?.let { tm ->
            tm.suspendAll()
            tm.list().forEach { tab -> SecureWebViewFactory.tearDown(tab.webView) }
        }
        super.onDestroy()
    }

    override fun onPause() {
        // 应用转后台或进入系统遮罩时没有持续可见的明确同意；恢复后必须重新请求审批。
        viewModel.rejectPendingNavigationConfirmation()
        super.onPause()
    }
}

/** 页面容器：显示当前标签的 WebView（两种布局共用）。 */
@Composable
private fun WebContentArea(
    tabManager: TabManager,
    modifier: Modifier = Modifier,
) {
    AndroidView(
        modifier = modifier.fillMaxWidth(),
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
}

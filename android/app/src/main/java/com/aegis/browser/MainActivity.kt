package com.aegis.browser

import android.view.KeyEvent
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.WebView
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

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
        // A1：System WebView 版本检查（CVE-2026-12438/11295 防御——
        // 过旧则提示更新，不阻塞浏览）
        WebViewVersionCheck.checkAndPrompt(this) { viewModel.setWebViewAlert(it) }
        // 初始化 ViewModel（TabManager + 首个标签）
        viewModel.init(this)

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

                Column(modifier = Modifier.fillMaxSize()) {
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
                        AddressBarWithSnake(
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

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            val wv = viewModel.currentWebViewOrNull()
            // 消费 WebView 历史栈逐级回退；无历史（如首页）放行系统默认
            if (wv != null && wv.canGoBack()) {
                SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(HistoryAction.BACK)
                return true
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        // Activity 销毁是确认 UI 的退出边界；任何待审批导航均须先撤销，不留可恢复能力。
        viewModel.rejectPendingNavigationConfirmation()
        // 释放全部 WebView 持有的 Chromium 资源
        viewModel.getTabManager()?.let { tm ->
            tm.suspendAll()
            tm.list().forEach { tab ->
                tab.webView.stopLoading()
                tab.webView.loadUrl("about:blank")
                tab.webView.destroy()
            }
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

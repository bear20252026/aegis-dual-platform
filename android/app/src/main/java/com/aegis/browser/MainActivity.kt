package com.aegis.browser

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
import androidx.compose.foundation.layout.padding
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

                // A1：版本过旧 → 安全提示对话框（CVE-2026-12438/11295 防御）
                webViewAlert?.let { msg ->
                    AlertDialog(
                        onDismissRequest = { viewModel.dismissWebViewAlert() },
                        title = { Text("安全提示") },
                        text = { Text(msg) },
                        confirmButton = {
                            TextButton(
                                onClick = {
                                    viewModel.dismissWebViewAlert()
                                    WebViewVersionCheck.openUpdate(this@MainActivity)
                                },
                            ) { Text("去更新") }
                        },
                        dismissButton = {
                            TextButton(onClick = { viewModel.dismissWebViewAlert() }) { Text("稍后") }
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
                        AddressBarAndNav(
                            address = address,
                            onAddressChange = { viewModel.updateAddress(it) },
                            onOpen = { viewModel.navigateToAddress() },
                            onBack = { viewModel.navigateHistory(HistoryAction.BACK) },
                            onForward = { viewModel.navigateHistory(HistoryAction.FORWARD) },
                            onReload = { viewModel.navigateHistory(HistoryAction.RELOAD) },
                        )
                        WebContentArea(tabManager = viewModel.getTabManager()!!, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }

    override fun onDestroy() {
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
}

/** 地址栏 + 导航按钮（top 布局专用，抽离保持薄壳；按钮功能经回调上抛）。 */
@Composable
private fun AddressBarAndNav(
    address: String,
    onAddressChange: (String) -> Unit,
    onOpen: () -> Unit,
    onBack: () -> Unit,
    onForward: () -> Unit,
    onReload: () -> Unit,
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            OutlinedTextField(
                value = address,
                onValueChange = onAddressChange,
                modifier = Modifier.weight(1f),
                singleLine = true,
                label = { Text("地址") },
            )
            Button(onClick = onOpen) { Text("打开") }
        }
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Button(onClick = onBack) { Text("后退") }
            Button(onClick = onForward) { Text("前进") }
            Button(onClick = onReload) { Text("刷新") }
        }
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

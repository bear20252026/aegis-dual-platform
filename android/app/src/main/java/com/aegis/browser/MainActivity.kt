package com.aegis.browser

import android.os.Bundle
import android.view.ViewGroup
import android.webkit.WebView
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
    private lateinit var tabManager: TabManager

    // A1（final-development-checklist）：System WebView 版本过旧提示文案（null=不提示）
    private var webViewAlertMessage: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        tabManager = TabManager()
        // A1：System WebView 版本检查（CVE-2026-12438/11295 防御——
        // 过旧则提示更新，不阻塞浏览）
        WebViewVersionCheck.checkAndPrompt(this) { webViewAlertMessage = it }
        tabManager.addTab(
            SecureWebViewFactory.create(this),
            url = "https://www.bing.com",
        )

        setContent {
            AegisTheme {
                var tabs by remember { mutableStateOf(tabManager.list()) }
                var activeIndex by remember { mutableStateOf(tabManager.activeIndex) }
                var address by remember { mutableStateOf("https://www.bing.com") }
                // 落地 B：标签栏布局（默认 top；可在设置中切换 left）
                var tabsPosition by remember { mutableStateOf("top") }
                // A1：System WebView 版本过旧提示（null=不提示）
                var webViewAlert by remember { mutableStateOf(webViewAlertMessage) }

                fun refresh() {
                    tabs = tabManager.list()
                    activeIndex = tabManager.activeIndex
                }

                fun newTab() {
                    tabManager.addTab(
                        SecureWebViewFactory.create(this@MainActivity),
                        url = "https://www.bing.com",
                    )
                    refresh()
                }

                // A1：版本过旧 → 安全提示对话框（CVE-2026-12438/11295 防御）
                webViewAlert?.let { msg ->
                    AlertDialog(
                        onDismissRequest = { webViewAlert = null },
                        title = { Text("安全提示") },
                        text = { Text(msg) },
                        confirmButton = {
                            TextButton(
                                onClick = {
                                    webViewAlert = null
                                    WebViewVersionCheck.openUpdate(this@MainActivity)
                                },
                            ) { Text("去更新") }
                        },
                        dismissButton = {
                            TextButton(onClick = { webViewAlert = null }) { Text("稍后") }
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
                                onSelect = { index ->
                                    tabManager.switchTo(index)
                                    refresh()
                                },
                                onClose = { index ->
                                    tabManager.closeTab(index)
                                    refresh()
                                },
                                onNewTab = ::newTab,
                            )
                            WebContentArea(tabManager = tabManager, modifier = Modifier.weight(1f))
                        }
                    } else {
                        TabBar(
                            tabs = tabs,
                            activeIndex = activeIndex,
                            onSelect = { index ->
                                tabManager.switchTo(index)
                                refresh()
                            },
                            onClose = { index ->
                                tabManager.closeTab(index)
                                refresh()
                            },
                            onNewTab = ::newTab,
                        )
                        AddressBarAndNav(
                            address = address,
                            onAddressChange = { address = it },
                            onOpen = {
                                val wv = tabManager.current()?.webView ?: return@AddressBarAndNav
                                BrowserEngine(wv).load(address)
                            },
                            // A-04 整改（国防级审查）：导航经统一策略层——
                            // 历史导航不加载新 URL（无需 URL 校验）；发布期
                            // 集中审计 + 地址栏状态同步（记录）
                            onBack = { tabManager.current()?.webView?.goBack() },
                            onForward = { tabManager.current()?.webView?.goForward() },
                            onReload = { tabManager.current()?.webView?.reload() },
                        )
                        WebContentArea(tabManager = tabManager, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        // 释放全部 WebView 持有的 Chromium 资源
        tabManager.suspendAll()
        tabManager.list().forEach { tab ->
            tab.webView.stopLoading()
            tab.webView.loadUrl("about:blank")
            tab.webView.destroy()
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

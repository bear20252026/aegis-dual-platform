package com.aegis.chromeui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier

/**
 * 阶段 D（蓝图 android/chrome-ui）：Compose 状态机 UI 骨架——地址栏/标签/错误页/
 * 原生确认（按调研：官方 Compose 状态管理——rememberSaveable/BackHandler——
 * 安全错误可见不静默）。状态转移由 broker 授权（ADR-002）——安全默认值。
 * 阶段 D 最小——完整 UI（地址栏输入/标签栏/确认对话框）按蓝图迭代。
 */
@Composable
fun BrowserScreen(
    state: BrowserState,
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    // 骨架：按 BrowserState 展示对应 UI（Active 渲染 WebView / Crashed 错误页
    // 可重试 / Restoring 恢复指示 / 其他状态提示）——安全错误对用户可见
    when (state) {
        BrowserState.Crashed -> ErrorPage(onRetry)  // 崩溃错误页（不自动放行——安全恢复）
        BrowserState.Restoring -> RestoringIndicator()
        else -> BrowserContainer(modifier)
    }
}

@Composable
private fun ErrorPage(onRetry: () -> Unit) {
    // 骨架：渲染器崩溃——安全错误可见——用户重试（恢复 URL 经 broker 策略重验）
}

@Composable
private fun RestoringIndicator() {
    // 骨架：进程重建恢复指示（不自动放行——URL 经 broker 重验）
}

@Composable
private fun BrowserContainer(modifier: Modifier) {
    // 骨架：WebView 容器（webview-adapter——导航经 broker 决策）
}

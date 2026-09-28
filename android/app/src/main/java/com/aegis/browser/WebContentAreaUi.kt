package com.aegis.browser

import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

// AD-101（审计 2026-09-23 清单·A6 批）：页面内容区组件文件——WebContentArea /
// PageErrorPanel / ErrorActionButton 自 MainActivity.kt 抽出（原文件超改造
// 红线；行为与视觉与抽取前逐行一致）。

/**
 * 页面容器：显示当前标签的 WebView（两种布局共用）。
 *
 * P2-1 修复（全面审计 2026-09-04）：错误状态非空时在内容区上方渲染
 * [PageErrorPanel]（原实现 SSL/加载错误静默白屏，无任何反馈）。
 *
 * AD-088/089（2026-09-26 审计）：AndroidView 以 [activeIndex] 为 key 显式
 * 重建并补 onRelease——key 化后切换即重建容器，离屏时 onRelease 摘除旧
 * WebView 引用（容器交还组合，WebView 生命周期仍归 TabManager/tearDown 所有）。
 *
 * @Suppress 与 AddressBarRow 同口径：回调装配点参数多系设计使然。
 */
@Suppress("FunctionNaming", "LongParameterList")
@Composable
internal fun WebContentArea(
    tabManager: TabManager,
    activeIndex: Int,
    pageError: PageError?,
    onRetry: () -> Unit,
    onBackToSafePage: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier) {
        key(activeIndex) {
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
                onRelease = { container ->
                    // AD-088：容器随组合释放，摘除 WebView 引用（防容器持有
                    // 已切走的标签 WebView——泄漏/双父挂载面）
                    container.removeAllViews()
                },
            )
        }
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
 *
 * AD-153（审计 2026-09-23 清单·A7 批）：遮罩/文字色经语义色板取色。
 */
@Suppress("FunctionNaming")
@Composable
private fun PageErrorPanel(
    error: PageError,
    onRetry: () -> Unit,
    onBackToSafePage: () -> Unit,
) {
    val chrome = LocalAegisChromeColors.current
    Box(
        modifier =
            Modifier
                .fillMaxSize()
                .background(chrome.errorOverlayBackground)
                .padding(UiDimens.ERROR_PANEL_PADDING.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(UiDimens.SPACING_MEDIUM.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = stringResource(if (error.isSsl) R.string.error_ssl_title else R.string.error_title),
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = error.description,
                color = chrome.textSecondary,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
            )
            Text(
                text = error.url,
                color = chrome.textSecondary,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
                maxLines = 2,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(UiDimens.SPACING_LARGE.dp)) {
                ErrorActionButton(textRes = R.string.error_retry, onClick = onRetry)
                ErrorActionButton(textRes = R.string.error_back_safe, onClick = onBackToSafePage)
            }
        }
    }
}

/**
 * 错误面板操作按钮（重试/返回安全页共用）。
 *
 * AD-173（审计 2026-09-23 清单·A7 批）：Surface+Text 冒充按钮 → Material3
 * Button——原自绘骨架没有 Material 按钮的禁用态/最小触摸目标/高度语义，
 * 与主题控件脱节。改用 M3 [Button]：容器色经语义色板（buttonOverlay，
 * 视觉与抽取前一致），圆角沿用圆形（CircleShape）不改变视觉。
 */
@Suppress("FunctionNaming")
@Composable
private fun ErrorActionButton(
    textRes: Int,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        shape = CircleShape,
        colors =
            ButtonDefaults.buttonColors(
                containerColor = LocalAegisChromeColors.current.buttonOverlay,
                contentColor = Color.White,
            ),
        contentPadding =
            PaddingValues(
                horizontal = UiDimens.ERROR_ACTION_PADDING_X.dp,
                vertical = UiDimens.SPACING_MEDIUM.dp,
            ),
    ) {
        Text(
            text = stringResource(textRes),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

package com.aegis.browser

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * 标签栏（单文件单职责：多标签的横向展示与交互）。
 *
 * 纯 UI 组件，不持有任何状态 —— 数据来自 [tabs]/[activeIndex]，
 * 交互通过回调上抛（[onSelect]/[onClose]/[onNewTab]），由调用方
 * （MainActivity + TabManager）处理。这保证 UI 可复用、可预览、
 * 逻辑与界面完全解耦。
 *
 * 玻璃风格（S5）：工具栏背景用半透明深蓝紫（与状态栏 #101827 同色系），
 * 视觉接近亚克力毛玻璃；所有文字/控件转白色保证深色底上的可读性。
 * 全版本兼容 —— 不依赖 Android 12+ 的 RenderEffect 模糊，仅用 alpha
 * 混合模拟，避免在 WebView 内容上做实时模糊的性能损耗。
 *
 * 标签胶囊骨架由 [TabChipCore] 单源提供（与 VerticalTabBar 共用）。
 *
 * AD-086（2026-09-26 审计）：激活标签变化时滚动到可视区——超宽横向
 * 标签栏此前溢出部分不可见（切到屏幕外标签无任何视觉反馈）。
 *
 * @param tabs       标签列表（含标题/URL）
 * @param activeIndex 当前激活标签索引
 * @param onSelect   点击标签切换（参数为索引）
 * @param onClose    点击标签关闭按钮（参数为索引）
 * @param onNewTab   点击"+"新建标签
 */
@Composable
fun TabBar(
    tabs: List<Tab>,
    activeIndex: Int,
    onSelect: (Int) -> Unit,
    onClose: (Int) -> Unit,
    onNewTab: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()
    LaunchedEffect(activeIndex, tabs.size) {
        if (activeIndex in tabs.indices) listState.animateScrollToItem(activeIndex)
    }
    // AD-153（审计 2026-09-23 清单·A7 批）：语义色板经主题取色
    val chrome = LocalAegisChromeColors.current
    LazyRow(
        state = listState,
        modifier =
            modifier
                .fillMaxWidth()
                .height(44.dp)
                .background(chrome.toolbarBackground),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        contentPadding = PaddingValues(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // AD-039：key=tab.id——标题变化（copy 替换实例）时复用既有 item 而非
        // 重建，且防关闭中间标签后索引位移引发的状态错位
        itemsIndexed(tabs, key = { _, tab -> tab.id }) { index, tab ->
            TabChipCore(
                tab = tab,
                active = index == activeIndex,
                modifier =
                    Modifier
                        .height(32.dp)
                        .widthIn(max = 200.dp),
                onSelect = { onSelect(index) },
                onClose = { onClose(index) },
            )
        }
        item {
            // AD-174（审计 2026-09-23 清单·A7 批）：新建控件单源 NewTabButton
            // （骨架/底色/语义与 VerticalTabBar 共用，差异仅形状/尺寸/文案）
            NewTabButton(
                label = "+",
                shape = CircleShape,
                modifier = Modifier.size(32.dp),
                onNewTab = onNewTab,
            )
        }
    }
}

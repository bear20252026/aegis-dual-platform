package com.aegis.browser

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

/**
 * 垂直标签栏（单文件单职责：多标签的纵向展示与交互）。
 *
 * 落地 B（借鉴 zen/floorp 垂直标签思路，适配 Kotlin Compose）：
 * - 固定左侧栏，标签纵向排列（LazyColumn），支持切换/关闭/新建；
 * - 纯 UI 组件，不持有状态 —— 数据来自 [tabs]/[activeIndex]，
 *   交互通过回调上抛，由 MainActivity + TabManager 处理；
 * - 玻璃风格与 [TabBar] 一致（半透明深蓝紫，全版本兼容）。
 *
 * AD-083/087（2026-09-26 审计）：删除分组渲染——Tab.group 字段全工程无
 * 写入点（假 parity，所有标签恒为「默认」组），分组标题永远渲染静态值；
 * 逐分组全量遍历 O(groups×tabs) 的结构随之移除，单次 itemsIndexed
 * O(tabs) 平铺渲染。工作区（分组/写入点）真实落地时随功能一起回归。
 *
 * 标签胶囊骨架由 [TabChipCore] 单源提供（与 TabBar 共用）。
 *
 * @param tabs        标签列表（含标题/URL）
 * @param activeIndex 当前激活标签索引
 * @param onSelect    点击标签切换（参数为索引）
 * @param onClose     点击标签关闭按钮（参数为索引）
 * @param onNewTab    点击"+ 新建标签"
 */
@Composable
fun VerticalTabBar(
    tabs: List<Tab>,
    activeIndex: Int,
    onSelect: (Int) -> Unit,
    onClose: (Int) -> Unit,
    onNewTab: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                .width(UiDimens.VERTICAL_TAB_BAR_WIDTH.dp)
                .fillMaxHeight()
                .background(LocalAegisChromeColors.current.toolbarBackground),
    ) {
        val listState = rememberLazyListState()
        // AD-223（2026-09-26 审计）：激活标签滚动对齐——AD-086 只给横向
        // TabBar 补了 animateScrollToItem；本栏 LazyColumn 超长标签列表切到
        // 屏幕外标签同样无视觉反馈，同口径补齐。
        LaunchedEffect(activeIndex, tabs.size) {
            if (activeIndex in tabs.indices) listState.animateScrollToItem(activeIndex)
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(UiDimens.TAB_BAR_SPACING.dp),
            verticalArrangement = Arrangement.spacedBy(UiDimens.VERTICAL_TAB_SPACING.dp),
        ) {
            // AD-040：key=tab.id（与 TabBar 同口径——复用 item + 防索引位移）
            itemsIndexed(tabs, key = { _, tab -> tab.id }) { index, tab ->
                TabChipCore(
                    tab = tab,
                    active = index == activeIndex,
                    modifier = Modifier.fillMaxWidth().height(UiDimens.VERTICAL_TAB_CHIP_HEIGHT.dp),
                    onSelect = { onSelect(index) },
                    onClose = { onClose(index) },
                )
            }
        }
        // AD-174（审计 2026-09-23 清单·A7 批）：新建控件单源 NewTabButton
        // （骨架/底色/语义与 TabBar 共用，差异仅形状/尺寸/文案）
        NewTabButton(
            label = "+ ${stringResource(R.string.cd_new_tab)}",
            shape = MaterialTheme.shapes.small,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(UiDimens.VERTICAL_NEW_TAB_BUTTON_PADDING.dp)
                    .height(UiDimens.VERTICAL_NEW_TAB_BUTTON_HEIGHT.dp),
            onNewTab = onNewTab,
        )
    }
}

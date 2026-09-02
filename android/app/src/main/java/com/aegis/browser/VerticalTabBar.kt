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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * 垂直标签栏（单文件单职责：多标签的纵向展示与交互）。
 *
 * 落地 B（借鉴 zen/floorp 垂直标签 + 工作区思路，适配 Kotlin Compose）：
 * - 固定左侧栏，标签纵向排列（LazyColumn），支持切换/关闭/新建；
 * - 按标签分组（group = 工作区）渲染分组标题，标签带分组标签；
 * - 纯 UI 组件，不持有状态 —— 数据来自 [tabs]/[activeIndex]，
 *   交互通过回调上抛，由 MainActivity + TabManager 处理；
 * - 玻璃风格与 [TabBar] 一致（半透明深蓝紫，全版本兼容）。
 *
 * 标签胶囊骨架由 [TabChipCore] 单源提供（与 TabBar 共用）。
 *
 * @param tabs        标签列表（含标题/URL/分组）
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
                .width(180.dp)
                .fillMaxHeight()
                .background(ToolbarBackground),
    ) {
        // 按分组渲染：先在 @Composable 上下文收集有序分组名（保留出现顺序）
        val groups = rememberOrderedGroups(tabs)
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(6.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            groups.forEach { group ->
                item(key = "group-$group") {
                    Text(
                        text = group,
                        style = MaterialTheme.typography.labelSmall,
                        color = GroupLabelColor,
                        modifier = Modifier.padding(start = 8.dp, top = 6.dp, bottom = 2.dp),
                    )
                }
                itemsIndexed(tabs) { index, tab ->
                    if (tab.group == group) {
                        TabChipCore(
                            tab = tab,
                            active = index == activeIndex,
                            modifier = Modifier.fillMaxWidth().height(34.dp),
                            titleModifier = Modifier.weight(1f),
                            onSelect = { onSelect(index) },
                            onClose = { onClose(index) },
                        )
                    }
                }
            }
        }
        Button(
            onClick = onNewTab,
            modifier = Modifier.fillMaxWidth().padding(6.dp).height(36.dp),
            colors =
                ButtonDefaults.buttonColors(
                    containerColor = ButtonOverlay,
                    contentColor = Color.White,
                ),
        ) {
            Text("+ 新建标签")
        }
    }
}

/** 记住分组的有序列表（按标签首次出现顺序去重，纯逻辑无副作用）。 */
@Composable
private fun rememberOrderedGroups(tabs: List<Tab>): List<String> {
    val seen = mutableSetOf<String>()
    val out = mutableListOf<String>()
    for (t in tabs) {
        val g = t.group.ifBlank { "默认" }
        if (seen.add(g)) out.add(g)
    }
    return out
}

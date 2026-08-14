package com.aegis.browser

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
    LazyRow(
        modifier = modifier
            .fillMaxWidth()
            .height(44.dp)
            .background(Color(0xCC101827)),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        contentPadding = PaddingValues(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        itemsIndexed(tabs) { index, tab ->
            TabChip(
                tab = tab,
                active = index == activeIndex,
                onSelect = { onSelect(index) },
                onClose = { onClose(index) },
            )
        }
        item {
            Button(
                onClick = onNewTab,
                modifier = Modifier.height(32.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(0x33FFFFFF),
                    contentColor = Color.White,
                ),
            ) {
                Text("+")
            }
        }
    }
}

/** 单个标签胶囊：标题 + 关闭按钮；激活态用更亮的半透明白高亮。 */
@Composable
private fun TabChip(
    tab: Tab,
    active: Boolean,
    onSelect: () -> Unit,
    onClose: () -> Unit,
) {
    Surface(
        onClick = onSelect,
        shape = MaterialTheme.shapes.small,
        color = if (active) Color(0x3DFFFFFF) else Color(0x1AFFFFFF),
        modifier = Modifier.height(32.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(start = 12.dp, end = 4.dp),
        ) {
            Text(
                text = tab.title.ifBlank { "新标签页" },
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                color = Color.White,
            )
            TextButton(
                onClick = onClose,
                modifier = Modifier.width(32.dp),
            ) {
                Text("×", color = Color.White)
            }
        }
    }
}

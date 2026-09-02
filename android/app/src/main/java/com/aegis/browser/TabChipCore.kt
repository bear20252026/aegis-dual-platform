package com.aegis.browser

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
 * 标签胶囊公共内核（单源）：横向标签栏（TabBar）与纵向标签栏（VerticalTabBar）
 * 共用同一个 Surface+Row+标题+关闭按钮骨架——此前两处各写一份、仅尺寸/前缀差异
 * （全库审计 2026-09-02 收敛重复 UI）。外层布局（横向 LazyRow / 纵向分组列表）
 * 仍由各标签栏文件自行负责。
 *
 * @param tab           标签数据（标题/固定标记）
 * @param active        激活态（更亮的半透明白高亮）
 * @param modifier      应用在 Surface 上的尺寸修饰（各标签栏自行定义）
 * @param titleModifier 应用在标题 Text 上的修饰（纵向栏传 weight(1f)）
 *
 * Composable 命名按 UI 惯例 PascalCase（既有基线同口径）；参数 6 个系
 * Surface 骨架单源化的设计使然（active/modifier/titleModifier 均带默认值）。
 */
@Suppress("FunctionNaming", "LongParameterList")
@Composable
internal fun TabChipCore(
    tab: Tab,
    active: Boolean,
    modifier: Modifier = Modifier,
    titleModifier: Modifier = Modifier,
    onSelect: () -> Unit,
    onClose: () -> Unit,
) {
    Surface(
        onClick = onSelect,
        shape = MaterialTheme.shapes.small,
        color = if (active) TabActiveHighlight else TabInactiveHighlight,
        modifier = modifier,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(start = 12.dp, end = 4.dp),
        ) {
            Text(
                text =
                    (if (tab.pinned) "\uD83D\uDCCC " else "") +
                        tab.title.ifBlank { "新标签页" },
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                color = Color.White,
                modifier = titleModifier,
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

package com.aegis.browser

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * 标签胶囊公共内核（单源）：横向标签栏（TabBar）与纵向标签栏（VerticalTabBar）
 * 共用同一个 Surface+Row+标题+关闭按钮骨架——此前两处各写一份、仅尺寸/前缀差异
 * （全库审计 2026-09-02 收敛重复 UI）。外层布局（横向 LazyRow / 纵向分组列表）
 * 仍由各标签栏文件自行负责。
 *
 * 2026-09-02 视觉重构：标题超出省略（防长标题把关闭钮挤出可视区）；
 * 关闭钮由 TextButton（最小触摸目标扩展会把「×」画出 32dp 槽位）改为
 * 紧凑圆钮，与外层胶囊边界对齐。
 *
 * AD-092（2026-09-26 审计）：关闭钮命中区扩到 32dp（胶囊内可用的最大尺寸，
 * 28→32 命中面积 +31%）——48dp 无障碍基线在 32/34dp 高的胶囊内放不下，且
 * Surface 按形状裁剪命中测试，超出胶囊边界的点击区无意义；字形仍居中 28dp
 * 视觉不变。
 *
 * AD-174（审计 2026-09-23 清单·A7 批）：「新建标签」控件单源——横向栏的
 * 圆形「+」与纵向栏的全宽「+ 新建标签」此前两套 Surface 骨架各自手写
 * （形状/尺寸/语义挂法各异，语义文案还重复读资源）。收敛为本文件内
 * [NewTabButton]：骨架、ButtonOverlay 底色、contentDescription 语义全部
 * 单源，形状/修饰/文案由调用方按布局注入。
 *
 * @param tab           标签数据（标题）
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
    val chrome = LocalAegisChromeColors.current
    Surface(
        onClick = onSelect,
        shape = MaterialTheme.shapes.small,
        color = if (active) chrome.tabActiveHighlight else chrome.tabInactiveHighlight,
        modifier = modifier,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(start = 12.dp, end = 2.dp),
        ) {
            Text(
                text = tab.title.ifBlank { TabManager.DEFAULT_TAB_TITLE },
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                color = Color.White,
                // weight(fill=false)：空间充裕时按内容收缩（横向胶囊不虚宽），
                // 空间紧张时让位给关闭钮——防长标题把「×」挤出胶囊。
                // 注意不能由调用方传 weight：VerticalTabBar 的调用点在
                // LazyItemScope，weight 会静默解析到外层 ColumnScope 变成 no-op。
                modifier = Modifier.weight(1f, fill = false).then(titleModifier),
            )
            // AD-043（2026-09-24 审计）：关闭钮补语义——contentDescription +
            // Role.Button（原纯「×」字形对 TalkBack 不可用）
            val closeDescription = stringResource(R.string.cd_tab_close)
            Box(
                contentAlignment = Alignment.Center,
                modifier =
                    Modifier
                        .size(32.dp)
                        .semantics {
                            contentDescription = closeDescription
                            role = Role.Button
                        }.clickable(onClick = onClose),
            ) {
                Text(
                    text = "×",
                    color = Color.White,
                    style = MaterialTheme.typography.bodySmall,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

/**
 * AD-174：「新建标签」按钮单源骨架（TabBar 与 VerticalTabBar 共用）。
 * Surface+Box+Text + ButtonOverlay 底色 + [R.string.cd_new_tab] 语义
 * 一处定义；横向栏传圆形紧凑修饰与「+」字形，纵向栏传全宽修饰与
 * 「+ 新建标签」文案——视觉差异全部经参数表达，不再复制骨架。
 *
 * Composable 命名按 UI 惯例 PascalCase（与 [TabChipCore] 同口径）。
 */
@Suppress("FunctionNaming")
@Composable
internal fun NewTabButton(
    label: String,
    shape: Shape,
    modifier: Modifier = Modifier,
    onNewTab: () -> Unit,
) {
    val chrome = LocalAegisChromeColors.current
    val newTabDescription = stringResource(R.string.cd_new_tab)
    Surface(
        onClick = onNewTab,
        shape = shape,
        color = chrome.buttonOverlay,
        modifier = modifier.semantics { contentDescription = newTabDescription },
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = label,
                color = Color.White,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

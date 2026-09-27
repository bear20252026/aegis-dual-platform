package com.aegis.browser

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp

// AD-101（审计 2026-09-23 清单·A6 批）：地址栏 + 导航按钮组件文件——
// 从 MainActivity.kt 抽出（原文件 610 行超改造红线 500；「抽组件」拆分，
// 非注释瘦身）。行为与视觉与抽取前逐行一致。

/** AD-064：禁用按钮灰显透明度（detekt MagicNumber 提取常量）。 */
private const val DISABLED_BUTTON_ALPHA = 0.4f

/**
 * 地址栏 + 导航按钮（纯浏览态）。
 *
 * 2026-09-02 视觉重构：两行大按钮改为单行——玻璃圆钮（后退/前进/刷新/阅读/翻译）
 * + 深色玻璃胶囊地址栏；「打开」并入地址栏尾部按键与 IME「搜索」动作。
 *
 * AD-064：后退/前进按历史可用性禁用（无历史时灰显且不可点）。
 *
 * Suppress 与 ChromeIconButton 同口径：Composable PascalCase 命名 +
 * 回调装配点参数多（AD-064 新增 canGoBack/canGoForward 后触发阈值）。
 */
@Suppress("FunctionNaming", "LongParameterList")
@Composable
internal fun AddressBarRow(
    address: String,
    canGoBack: Boolean,
    canGoForward: Boolean,
    onAddressChange: (String) -> Unit,
    onOpen: () -> Unit,
    onBack: () -> Unit,
    onForward: () -> Unit,
    onReload: () -> Unit,
    onReader: () -> Unit,
    onTranslate: () -> Unit,
    onToggleLayout: () -> Unit,
) {
    Row(
        modifier =
            Modifier
                .fillMaxWidth()
                .padding(horizontal = UiDimens.SPACING_MEDIUM.dp, vertical = UiDimens.SPACING_SMALL.dp),
        horizontalArrangement = Arrangement.spacedBy(UiDimens.SPACING_SMALL.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // AD-153（审计 2026-09-23 清单·A7 批）：语义色板经主题取色
        val chrome = LocalAegisChromeColors.current
        ChromeIconButton(stringResource(R.string.cd_back), "←", canGoBack, onBack)
        ChromeIconButton(stringResource(R.string.cd_forward), "→", canGoForward, onForward)
        ChromeIconButton(stringResource(R.string.cd_reload), "⟳", true, onReload)
        // AD-251：标签栏布局切换（top 横排 ↔ left 垂直）
        ChromeIconButton(stringResource(R.string.cd_toggle_layout), "⇅", true, onToggleLayout)
        OutlinedTextField(
            value = address,
            onValueChange = onAddressChange,
            modifier = Modifier.weight(1f),
            singleLine = true,
            placeholder = { Text(stringResource(R.string.address_placeholder), color = chrome.textSecondary) },
            shape = CircleShape,
            colors =
                OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = chrome.fieldBorderFocused,
                    unfocusedBorderColor = chrome.fieldBorderIdle,
                    focusedContainerColor = chrome.fieldBackground,
                    unfocusedContainerColor = chrome.fieldBackground,
                    cursorColor = Color.White,
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White,
                ),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { onOpen() }),
            trailingIcon = {
                // AD-091（2026-09-26 审计）：「打开」补 Role.Button 语义且
                // 命中区扩到 48dp 最小交互尺寸（原裸 Text+clickable 目标
                // 过小，TalkBack 也不报按钮角色）
                Box(
                    contentAlignment = Alignment.Center,
                    modifier =
                        Modifier
                            .clickable(onClick = onOpen, role = Role.Button)
                            .minimumInteractiveComponentSize(),
                ) {
                    Text(
                        text = stringResource(R.string.address_open),
                        color = chrome.textSecondary,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(end = UiDimens.SPACING_SMALL.dp),
                    )
                }
            },
        )
        ChromeIconButton(stringResource(R.string.cd_reader), "阅", true, onReader)
        ChromeIconButton(stringResource(R.string.cd_translate), "译", true, onTranslate)
    }
}

/**
 * 玻璃圆钮：工具栏图标按钮（半透明白圆形 + 居中字符图标）。
 *
 * AD-042（2026-09-24 审计）：补 [contentDescription] 语义；[enabled] 为 false
 * 时灰显且不可点（AD-064）。
 *
 * AD-222（2026-09-26 审计）：语义无条件挂载——禁用控件对 TalkBack 不再静默。
 *
 * AD-153：底色经语义色板（buttonOverlay）取色。
 *
 * Composable 命名按 UI 惯例 PascalCase（与 [TabChipCore] 同口径）。
 */
@Suppress("FunctionNaming")
@Composable
internal fun ChromeIconButton(
    contentDescription: String,
    glyph: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        color = LocalAegisChromeColors.current.buttonOverlay,
        modifier =
            Modifier
                .semantics { this.contentDescription = contentDescription }
                .alpha(if (enabled) 1f else DISABLED_BUTTON_ALPHA)
                .size(UiDimens.ICON_BUTTON_SIZE.dp),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(text = glyph, color = Color.White, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

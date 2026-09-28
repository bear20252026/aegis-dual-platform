package com.aegis.browser

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.colorResource

/**
 * chrome 语义色板（单文件单职责：集中管理标签栏/工具栏配色槽位，供
 * MainActivity/TabBar/VerticalTabBar/TabChipCore/AddressBarUi/WebContentAreaUi
 * 共用）。玻璃风格（S5）：深蓝紫背景 + 半透明白叠加（视觉接近亚克力毛玻璃）。
 *
 * AD-153（审计 2026-09-23 清单·A7 批）：色彩汇入语义槽位——原 UiColors.kt 是
 * 一组裸 Compose [Color] 顶层常量，调用点直接引用「原始色」而非「语义色」；
 * 现收敛为 [AegisChromeColors] 不可变数据类 + [LocalAegisChromeColors]
 * CompositionLocal，由 [AegisTheme] 在组合期装配提供——UI 组件只面向
 * 语义槽位（如 chromeBackground/tabActiveHighlight）取色。
 *
 * AD-187（审计 2026-09-23 清单·A7 批）：颜色单源迁 colors.xml——本文件
 * 与 res/values/colors.xml 曾双源持有同一批 hex（调色漏改任一处即漂移）。
 * 现原始色值只存在于 colors.xml，组合期经 colorResource 装配进语义槽位
 * （见 [aegisChromeColors]）；本文件不再持有任何原始色值。
 */
@Immutable
data class AegisChromeColors(
    /** 窗口实底（edge-to-edge 下状态栏/导航栏挖空区衬底 + 页面区背景）。 */
    val chromeBackground: Color,
    /** 工具栏/标签栏背景（半透明深蓝紫）。 */
    val toolbarBackground: Color,
    /** 按钮半透明白叠加（新建标签/玻璃圆钮底色）。 */
    val buttonOverlay: Color,
    /** 激活标签高亮（较亮的半透明白）。 */
    val tabActiveHighlight: Color,
    /** 非激活标签底（较暗的半透明白）。 */
    val tabInactiveHighlight: Color,
    /** 地址栏胶囊底色（深色玻璃）。 */
    val fieldBackground: Color,
    /** 地址栏胶囊描边（聚焦档）。 */
    val fieldBorderFocused: Color,
    /** 地址栏胶囊描边（默认档）。 */
    val fieldBorderIdle: Color,
    /** 次级文字（地址栏占位符/错误面板辅助文案）。 */
    val textSecondary: Color,
    /** 页面错误面板遮罩（深蓝紫近实底半透明——P2-1 修复引入）。 */
    val errorOverlayBackground: Color,
)

/**
 * chrome 语义色板的组合_local_。缺省即抛错（fail-fast）：必须在
 * [AegisTheme] 内消费——绕过主题取色正是 AD-153 要消除的路径。
 */
val LocalAegisChromeColors =
    staticCompositionLocalOf<AegisChromeColors> {
        error("AegisChromeColors 必须经 AegisTheme 提供（不得绕过主题取色）")
    }

/**
 * AD-187：从 colors.xml 单源装配语义色板（组合期调用，AegisTheme 消费）。
 * 资源名与 [AegisChromeColors] 槽位一一对应（colors.xml 注释区锁定映射）。
 */
@Composable
internal fun aegisChromeColors(): AegisChromeColors =
    AegisChromeColors(
        chromeBackground = colorResource(R.color.chrome_background),
        toolbarBackground = colorResource(R.color.toolbar_background),
        buttonOverlay = colorResource(R.color.button_overlay),
        tabActiveHighlight = colorResource(R.color.tab_active_highlight),
        tabInactiveHighlight = colorResource(R.color.tab_inactive_highlight),
        fieldBackground = colorResource(R.color.field_background),
        fieldBorderFocused = colorResource(R.color.field_border_focused),
        fieldBorderIdle = colorResource(R.color.field_border_idle),
        textSecondary = colorResource(R.color.text_secondary),
        errorOverlayBackground = colorResource(R.color.error_overlay_background),
    )

/**
 * AD-190（审计 2026-09-23 清单·A7 批）：状态栏图标明暗单源派生——原实现
 * `isAppearanceLightStatusBars = false` 硬编码「图标永远浅色」，与 chrome
 * 底色无任何派生关系（底色改浅色系时状态栏图标即不可见）。现由 chrome
 * 底色的相对亮度（ITU-R BT.601 加权）推导：深底 → 浅色图标（返回 true），
 * 浅底 → 深色图标（返回 false）。底色取自 colors.xml 单源
 * （chrome_background——与 Compose 页面区背景同一资源）。
 *
 * 纯函数（Int 入参，零 Android 依赖）——JVM 单测直测。
 */
@Suppress("MagicNumber") // 加权系数/位掩码/阈值是亮度算法的定义本身
internal fun statusBarUsesLightIcons(backgroundArgb: Int): Boolean {
    val red = (backgroundArgb shr 16) and 0xFF
    val green = (backgroundArgb shr 8) and 0xFF
    val blue = backgroundArgb and 0xFF
    // 相对亮度（BT.601 加权，0..255 域）——与 androidx.core ColorUtils 无关的
    // 最小实现（仅图标明暗分型用，无需感知度线性化）
    val luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255.0
    return luminance <= 0.5
}

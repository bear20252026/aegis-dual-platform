package com.aegis.browser

/**
 * 布局尺寸常量表（单文件单职责，与 [UiColors] 同口径）。
 *
 * AD-078/090（2026-09-26 审计）：MainActivity 散落的 dp 魔法数收敛为命名
 * 常量——数值含义见名即知，统一调整时不必逐处追字面量。取值均为既有
 * 视觉值（本批次不改变任何布局尺寸）。
 */
internal object UiDimens {
    /** 小间距：地址栏行元素间距 / 确认对话框行距。 */
    const val SPACING_SMALL = 6

    /** 中间距：地址栏行水平内边距 / 错误面板行距 / 按钮垂直内边距。 */
    const val SPACING_MEDIUM = 10

    /** 大间距：错误面板操作按钮间距。 */
    const val SPACING_LARGE = 14

    /** 玻璃圆钮直径（后退/前进/刷新/阅读/翻译）。 */
    const val ICON_BUTTON_SIZE = 38

    /** 错误面板外层内边距。 */
    const val ERROR_PANEL_PADDING = 24

    /** 错误面板操作按钮水平内边距。 */
    const val ERROR_ACTION_PADDING_X = 22

    /** 阅读模式对话框正文最大高度。 */
    const val READER_DIALOG_MAX_HEIGHT = 420
}

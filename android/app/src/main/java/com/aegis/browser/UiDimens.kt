package com.aegis.browser

/**
 * 布局尺寸常量表（单文件单职责，与 [AegisChromeColors] 同口径）。
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

    // AD-324（2026-10-02 审计）：TabBar/VerticalTabBar 散落的 dp 字面量收敛
    // ——取值均为既有视觉值（本批次不改变任何布局尺寸）。

    /** 横向标签栏高度。 */
    const val TAB_BAR_HEIGHT = 44

    /** 标签胶囊横向间距 / 列表内边距（横/纵共用取值）。 */
    const val TAB_BAR_SPACING = 6

    /** 横向标签栏内容水平内边距。 */
    const val TAB_BAR_CONTENT_PADDING = 8

    /** 横向标签胶囊高度。 */
    const val TAB_CHIP_HEIGHT = 32

    /** 横向标签胶囊最大宽度（长标题截断预算）。 */
    const val TAB_CHIP_MAX_WIDTH = 200

    /** 横向「+」新建按钮尺寸（圆形直径）。 */
    const val TAB_NEW_BUTTON_SIZE = 32

    /** 垂直标签栏宽度。 */
    const val VERTICAL_TAB_BAR_WIDTH = 180

    /** 垂直标签胶囊间距。 */
    const val VERTICAL_TAB_SPACING = 2

    /** 垂直标签胶囊高度。 */
    const val VERTICAL_TAB_CHIP_HEIGHT = 34

    /** 垂直「+ 新建标签」按钮高度。 */
    const val VERTICAL_NEW_TAB_BUTTON_HEIGHT = 36

    /** 垂直「+ 新建标签」按钮水平外边距。 */
    const val VERTICAL_NEW_TAB_BUTTON_PADDING = 6
}

@file:Suppress("MagicNumber") // 颜色常量表：全部为命名常量定义，无函数体字面量

package com.aegis.browser

import androidx.compose.ui.graphics.Color

// UI 颜色常量表（单文件单职责：集中管理标签栏/工具栏配色，供 TabBar 与
// VerticalTabBar 共用）。detekt 基线收敛（工具链 P0）：把 MagicNumber
// 颜色字面量提取为命名常量，消除代码异味且便于统一调整配色。
// 玻璃风格（S5）：深蓝紫背景 + 半透明白叠加（视觉接近亚克力毛玻璃）。

/** 工具栏/标签栏背景（深蓝紫，与状态栏 #101827 同色系） */
val ToolbarBackground = Color(0xCC101827)

/** 按钮半透明白叠加（"+" 新建标签按钮底色） */
val ButtonOverlay = Color(0x33FFFFFF)

/** 激活标签高亮（较亮的半透明白） */
val TabActiveHighlight = Color(0x3DFFFFFF)

/** 非激活标签底（较暗的半透明白） */
val TabInactiveHighlight = Color(0x1AFFFFFF)

/** 分组标题文字（次级白色） */
val GroupLabelColor = Color(0x99FFFFFF)

/** 窗口实底（edge-to-edge 下状态栏/导航栏挖空区的衬底——与工具栏同色系不透明版） */
val ChromeBackground = Color(0xFF101827)

/** 地址栏胶囊底色（深色玻璃） */
val FieldBackground = Color(0x1FFFFFFF)

/** 地址栏胶囊描边（聚焦/默认两档） */
val FieldBorderFocused = Color(0x66FFFFFF)
val FieldBorderIdle = Color(0x2EFFFFFF)

/** 次级文字（地址栏占位符） */
val TextSecondary = Color(0xB3FFFFFF)

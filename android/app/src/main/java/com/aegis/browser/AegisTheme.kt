package com.aegis.browser

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * 全局统一字体（落地任务：res/font 引入 + MaterialTheme 统一 FontFamily）。
 *
 * 苹果风格（与 Windows 端 config.font_family 默认栈一致）：
 * - 英文：Inter（≈ SF Pro）
 * - 中文：Source Han Sans SC（≈ 苹方 PingFang SC）
 * 字体文件位于 res/font/（OFL 开源，可再分发），随包打包。
 */
val AegisFontFamily: FontFamily = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.source_han_sans_sc_regular, FontWeight.Normal),
    Font(R.font.source_han_sans_sc_medium, FontWeight.Medium),
)

/** 应用级 MaterialTheme：统一字体族，其余样式沿用 Material3 默认。 */
@Composable
fun AegisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        typography = Typography(
            bodySmall = TextStyle(
                fontFamily = AegisFontFamily,
                fontWeight = FontWeight.Normal,
                fontSize = 12.sp,
            ),
            bodyMedium = TextStyle(
                fontFamily = AegisFontFamily,
                fontWeight = FontWeight.Normal,
                fontSize = 14.sp,
            ),
            labelSmall = TextStyle(
                fontFamily = AegisFontFamily,
                fontWeight = FontWeight.Normal,
                fontSize = 11.sp,
            ),
        ),
        content = content,
    )
}

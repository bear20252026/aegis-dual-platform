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
val aegisFontFamily: FontFamily =
    FontFamily(
        // AD-245（2026-09-26 审计）：Normal 权重经 res/font XML 家族加载——
        // 此前 Inter 与 Source Han Sans SC 同以 FontWeight.Normal 并列声明，
        // Compose 按首个命中取 Inter（FontFamily 多 Font 同权重并列无逐字形
        // 回退），中文 glyph（Inter 无 CJK 字形）实际走系统默认字体；XML 家族
        // 同权重多条目在平台解析层构成回退链（拉丁取 Inter，CJK 回退思源黑体）。
        Font(R.font.aegis_font_family, FontWeight.Normal),
        Font(R.font.source_han_sans_sc_medium, FontWeight.Medium),
    )

/** 应用级 MaterialTheme：统一字体族，其余样式沿用 Material3 默认。 */
@Composable
fun AegisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        typography =
            Typography(
                bodySmall =
                    TextStyle(
                        fontFamily = aegisFontFamily,
                        fontWeight = FontWeight.Normal,
                        fontSize = 12.sp,
                    ),
                bodyMedium =
                    TextStyle(
                        fontFamily = aegisFontFamily,
                        fontWeight = FontWeight.Normal,
                        fontSize = 14.sp,
                    ),
                labelSmall =
                    TextStyle(
                        fontFamily = aegisFontFamily,
                        fontWeight = FontWeight.Normal,
                        fontSize = 11.sp,
                    ),
            ),
        content = content,
    )
}

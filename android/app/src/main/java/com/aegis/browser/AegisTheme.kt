package com.aegis.browser

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight

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

/**
 * AD-093（审计 2026-09-23 清单·A6 批）：Typography 全套样式补齐——原实现只
 * 覆写 bodySmall/bodyMedium/labelSmall 三档，其余 12 档（display/headline/
 * title/bodyLarge/labelLarge 等）回落 Material3 默认 FontFamily（系统字体），
 * 使用这些档位的组件（如 titleMedium 的错误面板标题）字体族不统一。
 * 以默认 Typography 为基底逐档 copy 换字体——字号/字重沿用 M3 默认不变形。
 */
@Composable
fun AegisTheme(content: @Composable () -> Unit) {
    val base = Typography()
    MaterialTheme(
        typography =
            Typography(
                displayLarge = base.displayLarge.copy(fontFamily = aegisFontFamily),
                displayMedium = base.displayMedium.copy(fontFamily = aegisFontFamily),
                displaySmall = base.displaySmall.copy(fontFamily = aegisFontFamily),
                headlineLarge = base.headlineLarge.copy(fontFamily = aegisFontFamily),
                headlineMedium = base.headlineMedium.copy(fontFamily = aegisFontFamily),
                headlineSmall = base.headlineSmall.copy(fontFamily = aegisFontFamily),
                titleLarge = base.titleLarge.copy(fontFamily = aegisFontFamily),
                titleMedium = base.titleMedium.copy(fontFamily = aegisFontFamily),
                titleSmall = base.titleSmall.copy(fontFamily = aegisFontFamily),
                bodyLarge = base.bodyLarge.copy(fontFamily = aegisFontFamily),
                bodyMedium = base.bodyMedium.copy(fontFamily = aegisFontFamily),
                bodySmall = base.bodySmall.copy(fontFamily = aegisFontFamily),
                labelLarge = base.labelLarge.copy(fontFamily = aegisFontFamily),
                labelMedium = base.labelMedium.copy(fontFamily = aegisFontFamily),
                labelSmall = base.labelSmall.copy(fontFamily = aegisFontFamily),
            ),
        content = content,
    )
}

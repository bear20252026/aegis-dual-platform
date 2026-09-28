package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.nio.file.Files
import java.nio.file.Path
import javax.xml.parsers.DocumentBuilderFactory

/**
 * AD-190/AD-187（审计 2026-09-23 清单·A7 批）：chrome 色板单源守护——
 * ①[statusBarUsesLightIcons] 亮度派生边界（状态栏图标明暗不再硬编码）；
 * ②colors.xml 色板注册矩阵（Kotlin 侧语义槽位经 colorResource 消费，
 * 原始色值只允许存在于 colors.xml——本测试锁定槽位名与取值，防双源
 * 回潮或漂移）。
 */
class ChromeColorSchemeTest {
    // ---------------- AD-190：状态栏图标明暗亮度派生 ----------------

    @Test
    fun darkChromeBackgroundUsesLightIcons() {
        // #101827（深蓝紫）——相对亮度远低于 0.5 阈值
        assertTrue(statusBarUsesLightIcons(0xFF101827.toInt()))
        assertTrue(statusBarUsesLightIcons(0xFF000000.toInt()))
    }

    @Test
    fun lightChromeBackgroundUsesDarkIcons() {
        assertTrue("白色底必须切深色图标", !statusBarUsesLightIcons(0xFFFFFFFF.toInt()))
        assertTrue(!statusBarUsesLightIcons(0xFFEEEEEE.toInt()))
    }

    @Test
    fun luminanceThresholdIsExclusiveAtHalf() {
        // 灰阶 127 → 亮度 ≈0.498（≤0.5，浅色图标）；128 → ≈0.502（深色图标）
        assertTrue(statusBarUsesLightIcons(0xFF7F7F7F.toInt()))
        assertFalse(statusBarUsesLightIcons(0xFF808080.toInt()))
    }

    @Test
    fun alphaChannelDoesNotAffectIconDerivation() {
        // 派生只看 RGB（状态栏衬底 alpha 不改变图标明暗语义）
        assertEquals(
            statusBarUsesLightIcons(0xFF101827.toInt()),
            statusBarUsesLightIcons(0x80101827.toInt()),
        )
    }

    // ---------------- AD-187：colors.xml 色板单源矩阵 ----------------

    /** 仓库内 android/app/src/main/res/values/colors.xml（布局无关定位）。 */
    private fun requireColorsXml(): Path {
        val namesDir =
            generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
                .take(8)
                .map {
                    it
                        .resolve("app")
                        .resolve("src")
                        .resolve("main")
                        .resolve("res")
                        .resolve("values")
                }.firstOrNull { Files.isRegularFile(it.resolve("colors.xml")) }
        return checkNotNull(namesDir?.resolve("colors.xml")) {
            "未找到 app/src/main/res/values/colors.xml（请在仓库内运行测试）"
        }
    }

    /** colors.xml 的 name → value 映射。 */
    private fun readColorTable(): Map<String, String> {
        val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(requireColorsXml().toFile())
        val nodes = doc.getElementsByTagName("color")
        val table = mutableMapOf<String, String>()
        for (i in 0 until nodes.length) {
            val element = nodes.item(i) as Element
            table[element.getAttribute("name")] = element.textContent.trim()
        }
        return table
    }

    @Test
    fun chromePaletteIsRegisteredInColorsXmlSingleSource() {
        val table = readColorTable()
        // 与 AegisChromeColors 语义槽位一一对应（aegisChromeColors 的
        // colorResource 映射矩阵）；取值为迁移前 UiColors.kt 的既有视觉值。
        val expected =
            mapOf(
                "chrome_background" to "#FF101827",
                "toolbar_background" to "#CC101827",
                "button_overlay" to "#33FFFFFF",
                "tab_active_highlight" to "#3DFFFFFF",
                "tab_inactive_highlight" to "#1AFFFFFF",
                "field_background" to "#1FFFFFFF",
                "field_border_focused" to "#66FFFFFF",
                "field_border_idle" to "#2EFFFFFF",
                "text_secondary" to "#B3FFFFFF",
                "error_overlay_background" to "#E6101827",
            )
        expected.forEach { (name, value) ->
            assertEquals("colors.xml 缺失或漂移的色板项: $name", value, table[name])
        }
    }

    @Test
    fun statusBarColorIsNotDuplicatedInColorsXml() {
        // chrome_status_bar 与 chrome_background 同值双源——AD-187 并入单源后
        // 不得复活（styles.xml 引 chrome_background）
        assertFalse(
            "chrome_status_bar 重复色源回归——状态栏/导航栏应引 chrome_background",
            readColorTable().containsKey("chrome_status_bar"),
        )
    }

    @Test
    fun chromeBackgroundDerivesLightIconsConsistently() {
        // 单源联动：colors.xml 的 chrome_background 取值经亮度派生得到的
        // 图标明暗，必须与真机既有行为一致（深底 → 浅色图标）
        val table = readColorTable()
        val argb = table["chrome_background"]!!.removePrefix("#").toLong(16).toInt()
        assertTrue(statusBarUsesLightIcons(argb))
    }
}

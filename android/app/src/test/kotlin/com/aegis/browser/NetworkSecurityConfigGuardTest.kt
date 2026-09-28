package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Document
import org.w3c.dom.Element
import java.nio.file.Files
import java.nio.file.Path
import javax.xml.parsers.DocumentBuilderFactory

/**
 * AD-182（审计 2026-09-23 清单·A7 批）：网络安全配置守护断言——
 * 「全局禁用明文」此前只存在于 XML 注释（无任何机械守护，改坏/删属性
 * 无门禁感知）。本测试锁定三层联防不变式：
 * ① manifest 显式挂接 network_security_config；
 * ② manifest 保持 usesCleartextTraffic="false"（API<24 / 部分 WebView 路径兜底）；
 * ③ base-config 保持 cleartextTrafficPermitted="false"（明文主闸）。
 */
class NetworkSecurityConfigGuardTest {
    /** 仓库内 android/app/src/main（布局无关定位，与 WallpaperPackagingTest 同法）。 */
    private fun requireMainDir(): Path =
        generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
            .take(8)
            .map { it.resolve("app").resolve("src").resolve("main") }
            .firstOrNull { Files.isRegularFile(it.resolve("AndroidManifest.xml")) }
            ?: error("未找到 app/src/main/AndroidManifest.xml（请在仓库内运行测试）")

    private fun parse(file: Path): Document =
        DocumentBuilderFactory
            .newInstance()
            .newDocumentBuilder()
            .parse(file.toFile())

    @Test
    fun manifestWiresNetworkSecurityConfig() {
        val doc = parse(requireMainDir().resolve("AndroidManifest.xml"))
        val application = doc.getElementsByTagName("application").item(0) as Element
        assertEquals(
            "manifest 必须挂接 @xml/network_security_config（缺失即回落平台默认放行明文）",
            "@xml/network_security_config",
            application.getAttribute("android:networkSecurityConfig"),
        )
    }

    @Test
    fun manifestKeepsCleartextTrafficDisabled() {
        val doc = parse(requireMainDir().resolve("AndroidManifest.xml"))
        val application = doc.getElementsByTagName("application").item(0) as Element
        assertEquals(
            "usesCleartextTraffic 必须保持 false（API<24 与部分 WebView 路径的双重保险）",
            "false",
            application.getAttribute("android:usesCleartextTraffic"),
        )
    }

    @Test
    fun baseConfigDisablesCleartextEverywhere() {
        val doc = parse(requireMainDir().resolve("res").resolve("xml").resolve("network_security_config.xml"))
        val baseConfigs = doc.getElementsByTagName("base-config")
        assertTrue("network_security_config 必须声明 base-config（全域明文主闸）", baseConfigs.length >= 1)
        for (i in 0 until baseConfigs.length) {
            val element = baseConfigs.item(i) as Element
            assertEquals(
                "base-config.cleartextTrafficPermitted 必须为 false",
                "false",
                element.getAttribute("cleartextTrafficPermitted"),
            )
        }
    }

    @Test
    fun noDomainSpecificCleartextExceptions() {
        // 守护矩阵的负向断言：不允许出现任何「按域放行明文」的 domain-config
        val doc = parse(requireMainDir().resolve("res").resolve("xml").resolve("network_security_config.xml"))
        assertFalse(
            "不得出现 domain-config（全域禁明文不允许按域豁免）",
            doc.getElementsByTagName("domain-config").length > 0,
        )
    }
}

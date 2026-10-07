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
 * 无门禁感知）。本测试锁定四层不变式（①②③ 为原三层联防，④ 为第八轮 ② 新增）：
 * ① manifest 显式挂接 network_security_config；
 * ② manifest 保持 usesCleartextTraffic="false"（API<24 / 部分 WebView 路径兜底）；
 * ③ base-config 保持 cleartextTrafficPermitted="false"（明文主闸）。
 * ④ 明文例外只允许**一个** domain-config 块，且域名与 includeSubdomains 逐条落在
 *    CLEARNTEXT_ALLOW_LIST 里（NSC 无 CIDR，网络层比 scheme 层的 LocalTargetHosts
 *    保守是有意的不对称）；云元数据/链路本地一类地址永不进白名单。
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
    fun cleartextExceptionsStayWithinTheBoundedAllowList() {
        // ②（第八轮 2026-10-07，用户定稿）：明文例外从「零例外」改为**有界白名单**。
        // 负向断言不能就这么消失——它换成四条更窄的：块数、属性显式性、域名逐条对账、
        // includeSubdomains 逐条对账（`.local`/`.internal` 一旦掉了子域匹配，
        // `my-nas.local` 就不在放行面内——「块看着在、实际没放行」与漏写属性同型）。
        val doc = parse(requireMainDir().resolve("res").resolve("xml").resolve("network_security_config.xml"))
        val blocks = doc.getElementsByTagName("domain-config")
        assertEquals("明文例外只允许一个 domain-config 块（多块会漏审）", 1, blocks.length)
        val block = blocks.item(0) as Element
        assertEquals(
            "例外块必须显式写 cleartextTrafficPermitted=\"true\"（省略属性即按 base-config 语义，" +
                "块看着在、实际没放行）",
            "true",
            block.getAttribute("cleartextTrafficPermitted"),
        )
        val names = domainNames(block)
        assertTrue("例外清单不得为空——空块等于把裁决关掉却看起来开着", names.isNotEmpty())
        val exceptions = linkedExceptions(block)
        assertEquals(
            "域名条目不得重复（重复会被 Map 折叠，白名单对账随之失真）",
            names.size,
            exceptions.size,
        )
        assertEquals(
            "例外域名超出白名单：新增条目要同批改本清单，并在注释里说明它为什么不是网段级放宽" +
                "（NSC 不支持 CIDR，网络层故意比 scheme 层的 LocalTargetHosts 保守）",
            emptySet<String>(),
            exceptions.keys - CLEARNTEXT_ALLOW_LIST.keys,
        )
        for ((name, includeSubdomains) in exceptions) {
            assertEquals(
                "$name 的 includeSubdomains 必须与白名单一致",
                CLEARNTEXT_ALLOW_LIST.getValue(name),
                includeSubdomains,
            )
        }
    }

    @Test
    fun nonDeviceAddressesNeverGetCleartext() {
        // 关键负向：白名单里绝不允许出现云元数据/链路本地/未指定地址——它们不是任何
        // 可访问设备，放行明文只会把 SSRF 面从 https 扩到 http。
        val doc = parse(requireMainDir().resolve("res").resolve("xml").resolve("network_security_config.xml"))
        val domains = exceptionDomainNames(doc)
        for (forbidden in listOf("169.254.169.254", "169.254.1.1", "0.0.0.0", "metadata.google.internal")) {
            assertFalse("$forbidden 不得进入明文例外", forbidden in domains)
        }
    }

    /** 例外块里的域名清单；一个例外块都没有时返回空面（块数由上一条用例判红）。 */
    private fun exceptionDomainNames(doc: Document): List<String> {
        val blocks = doc.getElementsByTagName("domain-config")
        if (blocks.length == 0) {
            return emptyList()
        }
        return domainNames(blocks.item(0) as Element)
    }

    private fun domainNames(block: Element): List<String> {
        val nodes = block.getElementsByTagName("domain")
        return (0 until nodes.length).map { nodes.item(it).textContent.trim() }
    }

    /** 域名 → includeSubdomains 字面量（判重复用 domainNames 的数量，不用 Map 折叠）。 */
    private fun linkedExceptions(block: Element): Map<String, String> {
        val nodes = block.getElementsByTagName("domain")
        val linked =
            (0 until nodes.length).associate { index ->
                val element = nodes.item(index) as Element
                element.textContent.trim() to element.getAttribute("includeSubdomains")
            }
        return linked
    }

    companion object {
        /**
         * 明文例外白名单（与 network_security_config.xml 逐条对账）。
         * `local`/`internal` 必须带子域匹配——NAS/打印机是 `my-nas.local` 这类名字，
         * 裸后缀本身在 NSC 里匹配不到任何东西。
         */
        private val CLEARNTEXT_ALLOW_LIST =
            mapOf(
                "localhost" to "false",
                "127.0.0.1" to "false",
                "local" to "true",
                "internal" to "true",
                "192.168.1.1" to "false",
            )
    }
}

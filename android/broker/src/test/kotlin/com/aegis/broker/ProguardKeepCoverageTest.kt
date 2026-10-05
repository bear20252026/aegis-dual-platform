package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * R8-AD-02（第八轮审计 2026-10-04）：JNA `Library` 接口的 keep 规则覆盖门禁。
 *
 * 为什么需要它：AD-219 曾为 probe 门禁的 JNA 接口补 keep 规则，却把名字写成
 * `com.aegis.broker.NativePolicyCoreGate$NativePolicyCoreAbi`（嵌套形态），而该接口在
 * `NativePolicyCoreGate.kt` 里是**顶层 private interface**（object 在 :105 已闭合，
 * :117 那行缩进为 0）——真实二进制名是 `com.aegis.broker.NativePolicyCoreAbi`。
 * 带 `$` 的规则命中 0 个类 ⇒ 方法名照旧被 R8 改名 ⇒ JNA 按名查符号失败 ⇒
 * `LinkageError` 折叠为 `Unavailable` ⇒ 门禁 block ⇒ 出货 APK 每次远程导航都拒
 * `native_policy_core_unavailable`；首页是 `file://` 不经 broker，于是形态是
 * 「进程存活 + 首页正常 + 所有网站打不开」，恰与 beta.51/beta.52 的启动存活型冒烟
 * 口径互补——那类验证抓不到它。
 *
 * 本门禁把「规则名 == 由声明位置推导出的二进制名」机械化：新增/移动/嵌套化任何
 * `: Library` 接口而漏改 proguard，当场转红。
 */
class ProguardKeepCoverageTest {
    /** 仓库内 android 目录（布局无关定位，与 NetworkSecurityConfigGuardTest 同法）。 */
    private fun requireAndroidDir(): Path =
        generateSequence(Paths.get(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
            .take(8)
            .firstOrNull { Files.isRegularFile(it.resolve("app").resolve("proguard-rules.pro")) }
            ?: error("未找到 app/proguard-rules.pro（请在仓库内运行测试）")

    private fun proguardText(): String =
        Files.readString(requireAndroidDir().resolve("app").resolve("proguard-rules.pro"))

    @Test
    fun everyJnaLibraryInterfaceIsKeptByName() {
        val names = libraryInterfaceBinaryNames(requireAndroidDir())
        val missing = missingKeepRules(proguardText(), names)
        assertEquals(
            "以下 JNA 接口缺少与之匹配的 -keep 规则（规则名与声明位置不符即属此列）：$missing",
            0,
            missing.size,
        )
    }

    @Test
    fun knownAbiInterfacesRemainInScanSurface() {
        // 覆盖面锚：防源文件改名/移动后本门禁静默扫到 0 个接口而恒绿
        val names = libraryInterfaceBinaryNames(requireAndroidDir())
        assertTrue("顶层 JNA 接口不在扫描面内：$names", names.contains(TOP_LEVEL_ABI))
        assertTrue("嵌套 JNA 接口不在扫描面内：$names", names.contains(NESTED_ABI))
    }

    @Test
    fun gateFailsWhenAKeepRuleIsMissing() {
        // 能失败：删掉一条真实 keep 规则，门禁必须报缺失——否则「加了断言却写不出
        // 失败用例」这个第七轮点名的形态在此复现。
        val names = libraryInterfaceBinaryNames(requireAndroidDir())
        assertTrue(missingKeepRules(proguardText(), names).isEmpty())
        val withoutOne = proguardText()
            .lines()
            .filterNot { it.contains("-keep interface $TOP_LEVEL_ABI ") }
            .joinToString("\n")
        val missing = missingKeepRules(withoutOne, names)
        assertEquals("删掉一条 keep 规则后必须报缺失：$missing", listOf(TOP_LEVEL_ABI), missing)
    }

    private fun missingKeepRules(
        rules: String,
        names: List<String>,
    ): List<String> = names.filter { name -> !rules.contains("-keep interface $name ") }

    /**
     * 扫描四个模块主源集，返回由声明位置推导出的 `: Library` 接口二进制名。
     *
     * 推导与 Kotlin 实际发出的二进制名一致：顶层声明 → `包名.名`；缩进声明（嵌套）→
     * `包名.外层类$名`。缩进判定取声明行的前导空格——ktlint 强制缩进，故该判据在本仓
     * 稳定。三引号原始串（内嵌 JS 有大量花括号与 `interface` 字样）整段跳过。
     */
    private fun libraryInterfaceBinaryNames(androidDir: Path): List<String> {
        val modules = listOf("broker", "app", "webview-adapter", "contracts")
        val out = mutableListOf<String>()
        for (module in modules) {
            val srcMain = androidDir.resolve(module).resolve("src").resolve("main")
            if (!Files.isDirectory(srcMain)) continue
            Files.walk(srcMain).use { stream ->
                stream
                    .filter { Files.isRegularFile(it) && it.toString().endsWith(".kt") }
                    .filter { !it.toString().replace('\\', '/').contains("/generated/") }
                    .forEach { file -> out += parseLibraryNames(Files.readString(file)) }
            }
        }
        assertTrue(
            "一个 `: Library` 接口都没扫到——判据已失效，本门禁沦为空转",
            out.isNotEmpty(),
        )
        return out
    }

    private fun parseLibraryNames(source: String): List<String> {
        val pkg = Regex("^package\\s+([\\w.]+)", RegexOption.MULTILINE)
            .find(source)?.groupValues?.get(1) ?: ""
        val declaration = Regex(
            "^(?:public\\s+|internal\\s+|private\\s+|abstract\\s+|open\\s+|sealed\\s+|data\\s+|enum\\s+)*" +
                "(?:class|interface|object)\\s+(\\w+)",
        )
        val found = mutableListOf<String>()
        var inRawString = false
        var lastTopLevel: String? = null
        for (line in source.split("\n")) {
            if (Regex("\"\"\"").findAll(line).count() % 2 == 1) inRawString = !inRawString
            if (inRawString) continue
            val indent = line.takeWhile { it == ' ' || it == '\t' }
            val trimmed = line.substring(indent.length)
            if (trimmed.startsWith("//")) continue
            declaration.find(trimmed)?.let { if (indent.isEmpty()) lastTopLevel = it.groupValues[1] }
            if (!trimmed.contains(": Library")) continue
            val name = Regex("interface\\s+(\\w+)").find(trimmed)?.groupValues?.get(1) ?: continue
            val nested = indent.isNotEmpty()
            found += if (nested && lastTopLevel != null) "$pkg.$lastTopLevel${'$'}$name" else "$pkg.$name"
        }
        return found
    }

    private companion object {
        val TOP_LEVEL_ABI = "com.aegis.broker.NativePolicyCoreAbi"
        val NESTED_ABI = "com.aegis.broker.NativePolicyCoreBridge${'$'}NativePolicyCoreAbi"
    }
}

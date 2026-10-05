package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * R8-AD-02（第八轮审计 2026-10-04）：JNA `Library` 接口的 keep 规则覆盖门禁。
 *
 * 为什么需要它：AD-219 曾为 probe 门禁的 JNA 接口补 keep 规则，却把名字写成
 * `com.aegis.broker.NativePolicyCoreGate$NativePolicyCoreAbi`（嵌套形态），而该接口在
 * `NativePolicyCoreGate.kt` 里是**顶层 private interface**——object 在 :105 已闭合，
 * :117 那行缩进为 0，真实二进制名是 `com.aegis.broker.NativePolicyCoreAbi`。带 `$` 的
 * 规则命中 0 个类 ⇒ R8 照旧改名 ⇒ JNA 按方法名查符号失败 ⇒ `LinkageError` 折叠为
 * `Unavailable` ⇒ 门禁 block ⇒ 每次远程导航拒 `native_policy_core_unavailable`；而首页
 * 是 `file://` 不经 broker，形态是「进程存活 + 首页正常 + 所有网站打不开」，恰与
 * beta.51/52 的「进程存活、UI 完整渲染」冒烟口径互补——那类验证抓不到它。
 * 同仓自证：`broker/detekt-baseline.xml` 对 Bridge 记作
 * `NativePolicyCoreBridge.NativePolicyCoreAbi`（嵌套带点号），对 Gate 记作裸名。
 *
 * 本门禁把「规则名 == 由声明位置推导出的二进制名」机械化：新增/移动/嵌套化任何
 * `: Library` 接口而漏改 proguard，当场转红。
 */
class ProguardKeepCoverageTest {
    private val topLevelAbi = "com.aegis.broker.NativePolicyCoreAbi"
    private val nestedAbi = "com.aegis.broker.NativePolicyCoreBridge" + NESTED_SEP + "NativePolicyCoreAbi"

    /** 仓库内 android 目录（布局无关定位，与 NetworkSecurityConfigGuardTest 同法）。 */
    private fun androidDir(): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val candidate = File(dir, "app/proguard-rules.pro")
            if (candidate.isFile) {
                return dir!!
            }
            dir = dir?.parentFile
        }
        error("未找到 app/proguard-rules.pro（请在仓库内运行测试）")
    }

    private fun proguardText(): String = File(androidDir(), "app/proguard-rules.pro").readText()

    @Test
    fun everyJnaLibraryInterfaceIsKeptByName() {
        val names = libraryInterfaceBinaryNames()
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
        val names = libraryInterfaceBinaryNames()
        assertTrue("顶层 JNA 接口不在扫描面内：$names", names.contains(topLevelAbi))
        assertTrue("嵌套 JNA 接口不在扫描面内：$names", names.contains(nestedAbi))
    }

    @Test
    fun gateFailsWhenAKeepRuleIsMissing() {
        // 能失败：删掉一条真实 keep 规则必须报缺失——否则「加了断言却写不出失败用例」
        // 这个第七轮点名的形态在此复现。
        val names = libraryInterfaceBinaryNames()
        assertTrue(missingKeepRules(proguardText(), names).isEmpty())
        val kept = proguardText().lines().filterNot { it.contains("-keep interface $topLevelAbi ") }
        val missing = missingKeepRules(kept.joinToString(" "), names)
        assertEquals("删掉一条 keep 规则后必须报缺失：$missing", listOf(topLevelAbi), missing)
    }

    private fun missingKeepRules(
        rules: String,
        names: List<String>,
    ): List<String> {
        return names.filter { name -> !rules.contains("-keep interface $name ") }
    }

    /**
     * 扫四模块主源集，返回由声明位置推导出的 `: Library` 接口二进制名。
     *
     * 推导与 Kotlin 实际发出的二进制名一致：顶层声明 → `包名.名`；缩进声明（嵌套）→
     * `包名.外层类$名`。缩进判据取声明行的前导空格——ktlint 强制缩进，故在本仓稳定。
     * 三引号原始串（内嵌 JS 有大量花括号与 `interface` 字样）整段跳过。
     */
    private fun libraryInterfaceBinaryNames(): List<String> {
        val out = mutableListOf<String>()
        for (module in modules) {
            val srcMain = File(androidDir(), "$module/src/main")
            if (!srcMain.isDirectory) {
                continue
            }
            for (file in srcMain.walkTopDown()) {
                if (isManagedSource(file)) {
                    out += parseLibraryNames(file.readText())
                }
            }
        }
        assertTrue("一个 `: Library` 接口都没扫到——判据已失效，本门禁沦为空转", out.isNotEmpty())
        return out
    }

    private fun isManagedSource(file: File): Boolean {
        if (!file.isFile || file.extension != "kt") {
            return false
        }
        return !file.invariantSeparatorsPath.contains("/generated/")
    }

    private fun parseLibraryNames(source: String): List<String> {
        var pkg = ""
        val packageFound = packageRegex.find(source)
        if (packageFound != null) {
            pkg = packageFound.groupValues[1]
        }
        val found = mutableListOf<String>()
        var inRawString = false
        var lastTopLevel = ""
        for (line in source.lines()) {
            if (rawQuote.findAll(line).count() % 2 == 1) {
                inRawString = !inRawString
            }
            if (inRawString) {
                continue
            }
            val indent = line.takeWhile { it == ' ' || it == '\t' }
            val trimmed = line.substring(indent.length)
            if (trimmed.startsWith("//")) {
                continue
            }
            if (indent.isEmpty()) {
                val declarationFound = declarationRegex.find(trimmed)
                lastTopLevel = if (declarationFound == null) "" else declarationFound.groupValues[1]
            }
            if (!trimmed.contains(": Library")) {
                continue
            }
            val interfaceFound = interfaceNameRegex.find(trimmed)
            if (interfaceFound == null) {
                continue
            }
            val name = interfaceFound.groupValues[1]
            val nested = indent.isNotEmpty() && lastTopLevel.isNotEmpty()
            found += if (nested) "$pkg.$lastTopLevel" + NESTED_SEP + name else "$pkg.$name"
        }
        return found
    }

    private companion object {
        const val NESTED_SEP = "\$"
        val modules = listOf("broker", "app", "webview-adapter", "contracts")
        val packageRegex = Regex("^package\\s+([\\w.]+)", RegexOption.MULTILINE)
        val declarationRegex = Regex(
            "^(?:public\\s+|internal\\s+|private\\s+|abstract\\s+" +
                "|open\\s+|sealed\\s+|data\\s+|enum\\s+)*"
                + "(?:class|object|interface)\\s+(\\w+)",
        )
        val interfaceNameRegex = Regex("interface\\s+(\\w+)")
        val rawQuote = Regex("\"\"\"")
    }
}

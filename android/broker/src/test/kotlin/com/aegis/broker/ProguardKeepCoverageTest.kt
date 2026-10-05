package com.aegis.broker

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
 * 反不遗漏设计（第八轮 CI 自证后重写）：推导判据本身可能漏文件（原始串跳过、
 * 正则形态漂移即静默少扫一格），故 everyDeclaredLibraryInterfaceIsAccountedFor
 * 本身可能漏文件（原始串/注释判据一漂移就静默少扫一格）。故 [everyDeclaredLibraryInterfaceIsAccountedFor]
 * 先把「主源集里 `: Library` 声明总数」与「推导出的名字数」对齐——漏扫当场转红，
 * 而不是退化成「少一条断言也算绿」。
 */
class ProguardKeepCoverageTest {
    private val topLevelAbi = "com.aegis.broker.NativePolicyCoreAbi"

    /** 仓库内 android 目录（布局无关定位，与 NetworkSecurityConfigGuardTest 同法）。 */
    private fun androidDir(): File {
        val start = File(System.getProperty("user.dir")).absoluteFile
        var dir: File? = start
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

    private fun mainSourceFiles(): List<File> {
        val out = mutableListOf<File>()
        for (module in modules) {
            val srcMain = File(androidDir(), "$module" + "/src/main")
            if (!srcMain.isDirectory) {
                continue
            }
            for (file in srcMain.walkTopDown()) {
                if (!file.isFile || file.extension != "kt") {
                    continue
                }
                if (file.invariantSeparatorsPath.contains("/generated/")) {
                    continue
                }
                out += file
            }
        }
        return out
    }

    @Test
    fun everyJnaLibraryInterfaceIsKeptByName() {
        val missing = missingKeepRules(proguardText(), libraryInterfaceBinaryNames())
        assertTrue(
            "以下 JNA 接口缺少匹配的 -keep 规则（规则名与声明位置不符即属此列）：$missing",
            missing.isEmpty(),
        )
    }

    @Test
    fun everyDeclaredLibraryInterfaceIsAccountedFor() {
        // 反不遗漏：`: Library` 的**声明行数**必须等于推导出的名字数。判据（原始串
        // 跳过、正则形态）一旦漂移漏扫一个文件，本断言当场转红，而不是让上一条用例
        // 在「少一条待检项」的状态下继续绿。
        var declared = 0
        for (file in mainSourceFiles()) {
            declared += file.readLines().count { it.trim().contains(": Library") }
        }
        val derived = libraryInterfaceBinaryNames().size
        assertTrue(
            "声明面 $declared 行与推导面 $derived 个名字不一致——扫描判据漏面",
            declared == derived,
        )
    }

    @Test
    fun gateTopLevelAbiIsDerivedAndKept() {
        val names = libraryInterfaceBinaryNames()
        assertTrue("顶层 JNA 接口不在推导面内：$names", names.contains(topLevelAbi))
        assertTrue(
            "推导出的顶层接口在 proguard 里没有对应 -keep",
            proguardText().contains("-keep interface $topLevelAbi "),
        )
    }

    @Test
    fun gateFailsWhenAKeepRuleIsMissing() {
        // 能失败：删掉那条真实 keep 规则必须让门禁报出它——否则「加了断言却写不出
        // 失败用例」这个第七轮点名的形态在此复现。
        val names = libraryInterfaceBinaryNames()
        assertTrue(missingKeepRules(proguardText(), names).isEmpty())
        val kept = proguardText().lines().filterNot { it.contains("-keep interface $topLevelAbi ") }
        val missing = missingKeepRules(kept.joinToString(" "), names)
        assertTrue("删掉一条 keep 规则后必须报出它，实得：$missing", missing.contains(topLevelAbi))
    }

    private fun missingKeepRules(
        rules: String,
        names: List<String>,
    ): List<String> = names.filter { name -> !rules.contains("-keep interface $name ") }

    /**
     * 由声明位置推导二进制名：顶层声明 → `包名.名`；嵌套声明 → `包名.外层类$名`。
     *
     * 外层判定用**花括号深度栈**而不是缩进——多行类头（`class X private constructor(`
     * 之后那行 0 缩进的 `) {`）会把「最后一个顶层声明」重置为空，第八轮 CI 就是这样
     * 把 Bridge 的接口推成了顶层名，与 Gate 的同名撞车。
     */
    private fun libraryInterfaceBinaryNames(): List<String> {
        val out = mutableListOf<String>()
        for (file in mainSourceFiles()) {
            out += parseLibraryNames(file.readText())
        }
        assertTrue("一个 `: Library` 接口都没扫到——判据失效，本门禁沦为空转", out.isNotEmpty())
        return out
    }

    private fun parseLibraryNames(source: String): List<String> {
        val packageFound = packageRegex.find(source)
        var pkg = ""
        if (packageFound != null) {
            pkg = packageFound.groupValues[1]
        }
        val found = mutableListOf<String>()
        val stack = ArrayDeque<Pair<String, Int>>()
        var depth = 0
        for (line in codeLines(source)) {
            found += libraryInterfaceName(line.trim(), pkg, stack, depth).orEmpty()
            pushDeclaration(line.trim(), stack, depth)
            depth += line.count { it == '{' } - line.count { it == '}' }
        }
        return found.filter { it.isNotEmpty() }
    }

    /** 整段跳过三引号原始串（内嵌 JS 有大量花括号）与整行注释。 */
    private fun codeLines(source: String): List<String> {
        val out = mutableListOf<String>()
        var inRawString = false
        for (line in source.lines()) {
            if (rawQuote.findAll(line).count() % 2 == 1) {
                inRawString = !inRawString
            }
            if (!inRawString && !line.trim().startsWith("//")) {
                out += line
            }
        }
        return out
    }

    private fun libraryInterfaceName(
        trimmed: String,
        pkg: String,
        stack: ArrayDeque<Pair<String, Int>>,
        depth: Int,
    ): String? {
        val wanted = trimmed.contains(": Library")
        val matched = if (wanted) interfaceNameRegex.find(trimmed) else null
        if (matched == null) {
            return null
        }
        val simple = matched.groupValues[1]
        if (simple == null) {
            return null
        }
        val outer = if (depth > 0) stack.lastOrNull()?.first else null
        return if (outer == null) "$pkg.$simple" else "$pkg.$outer$NESTED_SEP$simple"
    }

    /**
     * 压栈必须在 `: Library` 判定**之后**——否则接口自身那行会被当成外层，
     * 推出 `NativePolicyCoreAbi$NativePolicyCoreAbi` 这种假名字（第八轮孪生脚本实证）。
     */
    private fun pushDeclaration(
        trimmed: String,
        stack: ArrayDeque<Pair<String, Int>>,
        depth: Int,
    ) {
        val declarationFound = declarationRegex.find(trimmed)
        if (declarationFound == null) {
            return
        }
        val name = declarationFound.groupValues[1]
        while (stack.isNotEmpty() && stack.last().second >= depth) {
            stack.removeLast()
        }
        stack.addLast(name to depth)
    }

    private fun mainSourceFiles(): List<File> {
        val out = mutableListOf<File>()
        for (module in modules) {
            val srcMain = File(androidDir(), "$module/src/main")
            if (srcMain.isDirectory) {
                out += srcMain.walkTopDown().filter { isManagedSource(it) }
            }
        }
        return out
    }

    private fun isManagedSource(file: File): Boolean {
        val path = file.invariantSeparatorsPath
        val isKotlinSource = file.isFile && file.extension == "kt"
        return isKotlinSource && !path.contains("/generated/")
    }

    private companion object {
        const val NESTED_SEP = "\$"
        val modules = listOf("broker", "app", "webview-adapter", "contracts")
        val packageRegex = Regex("^package\\s+([\\w.]+)", RegexOption.MULTILINE)
        val declarationRegex = Regex("^(?!\s*fun\b)(?:\w+\s+)*(?:class|object|interface)\s+(\w+)")
        val interfaceNameRegex = Regex("interface\\s+(\\w+)")
        val rawQuote = Regex("\"\"\"")
    }
}

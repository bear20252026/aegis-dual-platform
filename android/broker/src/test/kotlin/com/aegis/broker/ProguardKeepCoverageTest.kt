package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * R8-AD-02（第八轮审计 2026-10-04）的常驻门禁：源码里每一个 JNA 映射接口
 * （`interface X : Library`）的**真实二进制名**都必须出现在
 * `android/app/proguard-rules.pro` 的 `-keep interface` 规则里。
 *
 * 为什么需要机器判定而不是注释：AD-219 把规则写成 `NativePolicyCoreGate$…`
 * （嵌套形态），而该接口在 `NativePolicyCoreGate.kt:117` 是**顶层 private
 * interface**（object 在 :105 已闭合，:117 缩进为 0），二进制名其实是
 * `com.aegis.broker.NativePolicyCoreAbi`。带 `$` 的规则命中 0 个类 ⇒ 方法名照旧
 * 被 R8 改名 ⇒ `Native.load` 按名查符号失败 ⇒ `LinkageError` 折叠为 Unavailable
 * ⇒ 门禁 block ⇒ 出货 APK 每次远程导航都拒 `native_policy_core_unavailable`。
 * 首页是 `file://` 不经 broker，所以现场形态是「进程存活、首页正常、所有网站
 * 打不开」——beta.51/52 那类「进程存活 + UI 完整渲染」的冒烟恰好抓不到。
 *
 * 同仓反向印证：`broker/detekt-baseline.xml` 对 Bridge 记作带点号的嵌套名、对
 * Gate 记作裸名——与本文件的推导口径一致。
 *
 * 推导面单独可断（[derivationSeparatesNestedFromTopLevelBinaryNames]）：它必须
 * 区分声明位置是嵌套还是顶层，否则本门禁退化成「文本里出现过某个含 Abi 的名
 * 字」——那正是 AD-219 当初骗过人的形态。
 */
class ProguardKeepCoverageTest {
    private fun repoRoot(): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val candidate = File(dir, PROGUARD_PATH)
            if (candidate.isFile) {
                return dir!!
            }
            dir = dir?.parentFile
        }
        error("未找到 $PROGUARD_PATH（请在仓库内运行测试）")
    }

    private fun brokerSources(root: File): List<File> {
        val dir = File(root, BROKER_SOURCE_DIR)
        val found = dir.listFiles { file: File -> file.isFile && file.name.endsWith(".kt") }
        if (found == null) {
            error("未找到 broker 源码目录：${dir.path}")
        }
        return found.sortedBy { it.name }
    }

    /**
     * 从源码行推导每个 `: Library` 接口的二进制名：顶层为 `包名.名`，嵌套为
     * `包名.外部$名`。判据只有缩进——Kotlin 的嵌套成员必在列 0 之外。
     */
    private fun jnaInterfaceNames(lines: List<String>): List<String> {
        val packageLine = lines.firstOrNull { it.startsWith("package ") }
        if (packageLine == null) {
            error("源文件缺 package 行")
        }
        val packageName = packageLine.removePrefix("package ").trim()
        val out = mutableListOf<String>()
        var owner: String? = null
        for (line in lines) {
            val columnZero = line.isNotEmpty() && !line.startsWith(" ") && !line.startsWith("\t")
            val abi = JNA_INTERFACE.find(line)
            if (abi != null) {
                val simple = abi.groupValues[1]
                val nestedIn = if (columnZero) null else owner
                out += qualifiedName(packageName, nestedIn, simple)
                continue
            }
            // 非 ABI 行：列 0 的顶层声明更新「当前外部名」——它是嵌套接口二进制名的
            // 前缀。缩进行不改状态，所以类体内的方法/属性不会把 owner 带偏。
            val top = if (columnZero) TOP_LEVEL_DECLARATION.find(line) else null
            if (top != null) {
                owner = top.groupValues[2]
            }
        }
        return out
    }

    private fun qualifiedName(packageName: String, owner: String?, simple: String): String {
        return if (owner == null) {
            "$packageName.$simple"
        } else {
            "$packageName.$owner$NESTED_SEPARATOR$simple"
        }
    }

    private fun derivedFromSources(root: File): List<String> {
        val names = mutableListOf<String>()
        for (file in brokerSources(root)) {
            names += jnaInterfaceNames(file.readLines())
        }
        return names.distinct().sorted()
    }

    private fun keptNames(proguardText: String): List<String> {
        val names = mutableListOf<String>()
        for (match in KEEP_RULE.findAll(proguardText)) {
            names += match.groupValues[1].trim()
        }
        return names
    }

    @Test
    fun derivationSeparatesNestedFromTopLevelBinaryNames() {
        // 本门禁自身的可失败面：把两种声明位置推成同一个名字就是失职。
        // 嵌套 → 带分隔符的外部名；顶层 → 裸名（AD-219 就是把后者写成前者，命中 0 个类）。
        val nestedSource =
            listOf(
                "package com.aegis.broker",
                "class Outer private constructor() {",
                "    private interface InnerAbi : Library {",
                "    }",
                "}",
            )
        val nestedExpected = listOf("com.aegis.broker.Outer" + NESTED_SEPARATOR + "InnerAbi")
        assertEquals(nestedExpected, jnaInterfaceNames(nestedSource))

        val flatSource =
            listOf(
                "package com.aegis.broker",
                "private interface FlatAbi : Library {",
                "}",
            )
        val flatExpected = listOf("com.aegis.broker.FlatAbi")
        assertEquals(flatExpected, jnaInterfaceNames(flatSource))
    }

    @Test
    fun derivationFindsBothRealInterfacesAndNothingElse() {
        // 实测面恰好两个：Bridge 的嵌套 Abi + Gate 的顶层 Abi。少一个说明推导器
        // 失配（新增 JNA 接口不会进门禁面），多一个说明它在乱抓文本。
        assertEquals(EXPECTED_BINARY_NAMES, derivedFromSources(repoRoot()))
    }

    @Test
    fun everyJnaInterfaceBinaryNameHasAKeepRule() {
        val root = repoRoot()
        val text = File(root, PROGUARD_PATH).readText()
        val kept = keptNames(text)
        assertTrue("proguard-rules.pro 里没有 -keep interface 规则——判定面为空", kept.isNotEmpty())
        for (name in derivedFromSources(root)) {
            val keptContainsName = kept.contains(name)
            assertTrue(
                "JNA 接口 $name 未被 -keep（AD-219 型失配：命中 0 个类的规则等于没有规则）",
                keptContainsName,
            )
        }
    }

    @Test
    fun nestedFormForGateInterfaceIsNeverResurrected() {
        // 反向锚：AD-219 那版写法必须报缺失——它命中 0 个类，却是「文本看着对」的形态
        val forbidden = "NativePolicyCoreGate" + NESTED_SEPARATOR + "NativePolicyCoreAbi"
        val text = File(repoRoot(), PROGUARD_PATH).readText()
        val absent = !text.contains(forbidden)
        assertTrue("不得出现嵌套形态的 Gate 接口规则：$forbidden", absent)
    }

    companion object {
        private const val PROGUARD_PATH = "android/app/proguard-rules.pro"
        private const val BROKER_SOURCE_DIR = "android/broker/src/main/kotlin/com/aegis/broker"

        // 嵌套二进制名的分隔符。提成常量而不在字符串里写嵌套模板——
        // WebViewHardening.kt:69 同源教训：复杂嵌套 `${}` 会让 ktlint 解析受阻。
        private const val NESTED_SEPARATOR = "\$"
        private val EXPECTED_BINARY_NAMES =
            listOf(
                "com.aegis.broker.NativePolicyCoreAbi",
                "com.aegis.broker.NativePolicyCoreBridge" + NESTED_SEPARATOR + "NativePolicyCoreAbi",
            )
        private val JNA_INTERFACE =
            Regex("(?:private |internal |public )?interface\\s+(\\w+)\\s*:[^;]*\\bLibrary\\b")
        private val TOP_LEVEL_DECLARATION =
            Regex("^(?:private |internal |public )?(class|object|interface)\\s+(\\w+)")
        private val KEEP_RULE =
            Regex("-keep\\s+interface\\s+(\\S+)\\s*\\{\\s*\\*;\\s*\\}")
    }
}

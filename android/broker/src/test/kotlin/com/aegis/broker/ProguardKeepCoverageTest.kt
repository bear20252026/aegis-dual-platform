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
 * 能区分声明位置是嵌套还是顶层，否则本门禁退化成「文本里出现过某个含 Abi 的
 * 名字」——那正是 AD-219 当初骗过人的东西。
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
        val files = dir.listFiles { file: File -> file.isFile && file.name.endsWith(".kt") }
            ?: error("未找到 broker 源码目录：${dir.path}")
        return files.sortedBy { it.name }
    }

    /**
     * 从源码行推导每个 `: Library` 接口的二进制名：顶层为 `包名.名`，嵌套为
     * `包名.外部$名`。判据只有缩进——Kotlin 的嵌套成员必在列 0 之外。
     */
    private fun jnaInterfaceNames(lines: List<String>): List<String> {
        val packageName = lines.firstOrNull { it.startsWith("package ") }
            ?.removePrefix("package ")
            ?.trim()
            ?: error("源文件缺 package 行")
        val out = mutableListOf<String>()
        var owner: String? = null
        for (line in lines) {
            val columnZero = line.isNotEmpty() && !line.startsWith(" ") && !line.startsWith("\t")
            val abi = JNA_INTERFACE.find(line)
            if (abi != null) {
                val simple = abi.groupValues[1]
                val nestedIn = if (columnZero) null else owner
                out += if (nestedIn == null) {
                    "$packageName.$simple"
                } else {
                    "$packageName.$nestedIn${'$'}$simple"
                }
                continue
            }
            // 非 ABI 行：列 0 的顶层声明更新「当前外部名」——嵌套接口的二进制名前缀。
            // 缩进行不改状态，所以类体内的方法/属性不会把 owner 带偏。
            val top = if (columnZero) {
                TOP_LEVEL_DECLARATION.find(line)?.groupValues?.get(2)
            } else {
                null
            }
            if (top != null) {
                owner = top
            }
        }
        return out
    }

    private fun derivedFromSources(root: File): List<String> =
        brokerSources(root).flatMap { jnaInterfaceNames(it.readLines()) }.distinct().sorted()

    private fun keptNames(proguardText: String): List<String> =
        KEEP_RULE.findAll(proguardText).map { it.groupValues[1].trim() }.toList()

    @Test
    fun derivationSeparatesNestedFromTopLevelBinaryNames() {
        // 本门禁自身的可失败面：把两种声明位置推成同一个名字就是失职
        val nested = jnaInterfaceNames(
            listOf(
                "package com.aegis.broker",
                "class Outer private constructor() {",
                "    private interface InnerAbi : Library {",
                "    }",
                "}",
            ),
        )
        assertEquals(listOf("com.aegis.broker.Outer\$InnerAbi"), nested)

        val flat = jnaInterfaceNames(
            listOf(
                "package com.aegis.broker",
                "private interface FlatAbi : Library {",
                "}",
            ),
        )
        assertEquals(listOf("com.aegis.broker.FlatAbi"), flat)
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
        val kept = keptNames(File(root, PROGUARD_PATH).readText())
        assertTrue(
            "proguard-rules.pro 里没有任何 -keep interface 规则——判定面为空",
            kept.isNotEmpty(),
        )
        for (name in derivedFromSources(root)) {
            assertTrue(
                "JNA 接口 $name 未被 -keep（AD-219 型失配：命中 0 个类的规则等于没有规则）",
                kept.contains(name),
            )
        }
    }

    @Test
    fun nestedFormForGateInterfaceIsNeverResurrected() {
        // 反向锚：AD-219 那版写法必须报缺失——它命中 0 个类，却是「文本看着对」的形态
        val text = File(repoRoot(), PROGUARD_PATH).readText()
        assertTrue(
            "不得出现 NativePolicyCoreGate${'$'}NativePolicyCoreAbi 这类嵌套形态规则",
            !text.contains("NativePolicyCoreGate${'$'}NativePolicyCoreAbi"),
        )
    }

    companion object {
        private const val PROGUARD_PATH = "android/app/proguard-rules.pro"
        private const val BROKER_SOURCE_DIR = "android/broker/src/main/kotlin/com/aegis/broker"
        private val EXPECTED_BINARY_NAMES = listOf(
            "com.aegis.broker.NativePolicyCoreAbi",
            "com.aegis.broker.NativePolicyCoreBridge${'$'}NativePolicyCoreAbi",
        )
        private val JNA_INTERFACE =
            Regex("(?:private |internal |public )?interface\\s+(\\w+)\\s*:[^;]*\\bLibrary\\b")
        private val TOP_LEVEL_DECLARATION =
            Regex("^(?:private |internal |public )?(class|object|interface)\\s+(\\w+)")
        private val KEEP_RULE =
            Regex("-keep\\s+interface\\s+(\\S+)\\s*\\{\\s*\\*;\\s*\\}")
    }
}

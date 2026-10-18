package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Kotlin JNA 声明面 ⇄ 核心导出面 ⇄ 跨语言常量的对齐判据（R9-B95）。
 *
 * 这条判据此前**不存在**：核心侧 `c_abi/tests/export_surface.rs` 钉着 13 个导出的冻结清单，
 * Windows 侧的绑定与它逐字对齐，而 Android 侧「声明了哪些符号」没有任何机器核过——
 * 一个拼错的 `fun aegis_policy_core_...` 只会在运行期变成 `LinkageError`，折叠成
 * 「原生核心不可用」；而**根本没声明**的导出（本批之前正是 `update_host_denylist_json`）
 * 看起来一切正常，实际那条能力在 Android 从不存在。
 *
 * 方向是双向的：
 * · Kotlin 声明了核心没导出的 ⇒ 红（假绑定，运行期必炸）；
 * · 核心导出了而 Kotlin 一个都没声明 ⇒ 红（能力在 Android 静默缺席——就是今天这件事）。
 * 常量同理由源码文本对账，不靠注释里写的"应当同值"。
 */
class AbiSurfaceAlignmentTest {
    private val frozenExports: List<String> by lazy {
        val text = repoFile(EXPORTS_PATH).readText()
        val body = text.substringAfter("FROZEN_EXPORTS").substringBefore("];")
        val pattern = Regex("\"(aegis_policy_core[A-Za-z0-9_]*)\"")
        pattern.findAll(body).map { it.value.trim('"') }.toList()
    }

    private val kotlinDeclared: Set<String> by lazy {
        val dir = File(repoFile(BROKER_MODULE), "src/main/kotlin/com/aegis/broker")
        val files = dir.listFiles { file: File -> file.isFile && file.name.endsWith(".kt") }.orEmpty()
        assertTrue("找不到 broker 源文件：$dir", files.isNotEmpty())
        val names = mutableSetOf<String>()
        val pattern = Regex("fun (aegis_policy_core[A-Za-z0-9_]*)\\(")
        for (file in files) {
            val text = file.readText()
            if (text.contains(": Library")) {
                for (found in pattern.findAll(text)) {
                    names += found.groupValues[1]
                }
            }
        }
        names.toSet()
    }

    @Test
    fun bothSurfacesAreNonEmptyBeforeComparingThem() {
        // 正面控制：先证明两边都扫到了东西，否则下面的相等断言可能在「两个空集」上恒真
        assertTrue("核心导出清单只解析到 ${frozenExports.size} 项——扫描面塌了", frozenExports.size >= 13)
        assertTrue("Kotlin 侧只解析到 ${kotlinDeclared.size} 个 JNA 符号——扫描面塌了", kotlinDeclared.size >= 13)
    }

    @Test
    fun kotlinBindingsCoverExactlyTheFrozenCoreExports() {
        val missing = (frozenExports.toSet() - kotlinDeclared).sorted()
        val fictional = (kotlinDeclared - frozenExports.toSet()).sorted()
        assertEquals("核心导出了但 Android 没绑定（能力静默缺席）", emptyList<String>(), missing)
        assertEquals("Android 绑定了核心没有的符号（运行期 LinkageError）", emptyList<String>(), fictional)
    }

    @Test
    fun denylistModeConstantsMatchTheRustDefinitions() {
        val rust = repoFile(DENYLIST_PATH).readText()
        assertSameInt(rustConst(rust, "MODE_APPEND", "i32"), CoreDenylistPush.MODE_APPEND, "MODE_APPEND")
        assertSameInt(rustConst(rust, "MODE_REPLACE", "i32"), CoreDenylistPush.MODE_REPLACE, "MODE_REPLACE")
        assertSameInt(rustConst(rust, "MODE_BEGIN", "i32"), CoreDenylistPush.MODE_BEGIN, "MODE_BEGIN")
        assertSameInt(rustConst(rust, "MODE_COMMIT", "i32"), CoreDenylistPush.MODE_COMMIT, "MODE_COMMIT")
    }

    @Test
    fun denylistBoundConstantsMatchTheRustDefinitions() {
        val rust = repoFile(DENYLIST_PATH).readText()
        // 漂了的后果各不相同：条目上限漂 = 核心按自己的口径拒条目；批次上限漂 = Android 造出必被拒的批次
        assertSameInt(rustConst(rust, "MAX_ENTRY_BYTES", "usize"), ThreatHostFeed.MAX_ENTRY_BYTES, "MAX_ENTRY_BYTES")
        assertSameInt(rustConst(rust, "MAX_BATCH_BYTES", "usize"), ThreatHostFeed.MAX_BATCH_BYTES, "MAX_BATCH_BYTES")
        assertTrue(
            "批次预算必须严格小于核心上限（撞上限的那一批是被拒绝，不是被截断）",
            ThreatHostFeed.CHUNK_PAYLOAD_BYTES < ThreatHostFeed.MAX_BATCH_BYTES,
        )
    }

    private fun assertSameInt(
        fromRust: Int,
        fromKotlin: Int,
        name: String,
    ) = assertEquals("$name 两侧不同值（跨语言常量漂了）", fromRust.toLong(), fromKotlin.toLong())

    private fun rustConst(
        text: String,
        name: String,
        type: String,
    ): Int {
        val found = Regex("const $name: $type = ([^;]+);").find(text)
        if (found == null) {
            throw AssertionError("Rust 源码里找不到常量 $name（改名了？那这条判据要同改）")
        }
        // RHS 可以是 `256` 也可以是 `64 * 1024`：按乘积求值——把算式形态误报成「找不到」
        // 是让判据哭狼的第一类错误，所以这里不复用"只吃纯数字"的正则。
        val parts = found.groupValues[1].split("*")
        var product = 1
        for (part in parts) {
            product *= part.trim().toInt()
        }
        return product
    }

    private fun repoFile(relative: String): File {
        var dir: File? = File(".").absoluteFile
        repeat(8) {
            val candidate = File(dir, relative)
            if (candidate.exists()) {
                return candidate
            }
            dir = dir?.parentFile
        }
        throw AssertionError("仓库内找不到 $relative（请在仓库内运行测试）")
    }

    private companion object {
        const val EXPORTS_PATH = "core/rust-policy-core/src/c_abi/tests/export_surface.rs"
        const val DENYLIST_PATH = "core/rust-policy-core/src/ffi/broker/denylist.rs"
        const val BROKER_MODULE = "android/broker"
    }
}

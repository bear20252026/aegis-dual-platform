package com.aegis.browser

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path

/**
 * AD-207（审计 2026-09-23 清单·A7 批）：搜索归一判定跨端共享向量测试——
 * 「搜索词 vs 网址」此前只有散点断言、无机器可读的共享向量（Windows
 * normalize_url 与 Android SearchEngines 各写各的用例，跨端语义漂移无
 * 单一锚点）。现以 JSON 向量文件为单一事实源：
 * - 文件位于 app/src/test/resources/search-normalize-vectors.json
 *   （当前仅 Android 侧消费——Windows 输入层补 scheme 的判据不同口径，R8-CS-SEC-15）；
 * - 本测试逐条驱动 classifyInput（判定）与 normalizeInput（归一链），
 *   expected_url=null 的条目只断言判定类（URL 值依赖引擎选择，跨端不锁）。
 */
class SearchNormalizeVectorsTest {
    private companion object {
        const val VECTOR_RESOURCE = "/search-normalize-vectors.json"
    }

    private fun loadVectors(): List<JSONObject> {
        // 双路径取资源：①测试类路径（Gradle test resources）；②仓库文件
        // 直读兜底（工作目录布局漂移时仍可运行）。
        val stream = javaClass.getResourceAsStream(VECTOR_RESOURCE)
        val payload =
            if (stream != null) {
                stream.bufferedReader().use { it.readText() }
            } else {
                val file =
                    locateTestResource()
                        ?: error("找不到共享向量 $VECTOR_RESOURCE（类路径与仓库均未命中）")
                String(Files.readAllBytes(file), Charsets.UTF_8)
            }
        return JSONObject(payload)
            .getJSONArray("vectors")
            .let { arr -> (0 until arr.length()).map { arr.getJSONObject(it) } }
    }

    private fun locateTestResource(): Path? =
        generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
            .take(8)
            .map {
                it
                    .resolve("src")
                    .resolve("test")
                    .resolve("resources")
                    .resolve("search-normalize-vectors.json")
            }.firstOrNull { Files.isRegularFile(it) }

    @Test
    fun sharedVectorsDriveClassifyAndNormalize() {
        val vectors = loadVectors()
        org.junit.Assert.assertTrue("共享向量不得为空", vectors.isNotEmpty())
        vectors.forEach { vector ->
            val input = vector.getString("input")
            val expectedKind = vector.getString("expected_kind")
            assertEquals(
                "classifyInput 漂移（input=「$input」）",
                expectedKind,
                SearchEngines.classifyInput(input).name,
            )
            // 归一链与判定必须自洽：拒绝类判定 → normalizeInput 必为 null
            if (expectedKind == "EMPTY" || expectedKind == "FORBIDDEN_SCHEME") {
                assertNull(
                    "判定 $expectedKind 但归一未拒绝（input=「$input」）",
                    SearchEngines.normalizeInput(input, SearchEngines.DEFAULT_ENGINE),
                )
            }
            // 期望 URL 明确给出的条目：全链输出精确锁定
            if (vector.has("expected_url") && !vector.isNull("expected_url")) {
                val expectedUrl = vector.getString("expected_url")
                assertEquals(
                    "normalizeInput 输出漂移（input=「$input」）",
                    expectedUrl,
                    SearchEngines.normalizeInput(input, SearchEngines.DEFAULT_ENGINE),
                )
            }
        }
    }

    @Test
    fun vectorFileIsRegisteredInResourceDirectory() {
        // 资源必须在 src/test/resources（Windows 侧按同一相对路径引用）——
        // 仅类路径命中不够，文件物理位置也是跨端契约的一部分
        assertNotNull("共享向量必须落位 app/src/test/resources", locateTestResource())
    }
}

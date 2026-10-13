package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * R9-B33（Q9）：严格百分号解码单源的行为面。
 *
 * 抽出来直测而不是只测调用方，是因为这次改的是「两份实现合成一份」：合并出错的形态
 * 不是逻辑变了，而是某条边界（`+`、孤立 `%`、多字节序列）在新家里悄悄换了语义。
 * 每条锚都写明「`java.net.URLDecoder` 会给什么」——那正是本项要与旧行为区别开的点。
 */
class PercentEncodingTest {
    private fun repoRoot(): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            if (File(dir, MAIN_SOURCE_DIR).isDirectory) {
                return dir!!
            }
            dir = dir?.parentFile
        }
        error("未找到 $MAIN_SOURCE_DIR（请在仓库内运行测试）")
    }

    @Test
    fun plusStaysLiteralInPath() {
        // URLDecoder.decode("a+b%2Eexe", "UTF-8") == "a b.exe"（query 语义）；
        // 路径里的 `+` 按 RFC 3986 是字面加号。
        assertEquals("a+b.exe", PercentEncoding.decodeStrict("a+b%2Eexe"))
    }

    @Test
    fun percentEscapesDecodeToTheirBytesAsOneUtf8Stream() {
        // 多字节序列必须整体按 UTF-8 解（逐字节劈开会得到乱码）
        assertEquals("报.pdf", PercentEncoding.decodeStrict("%E6%8A%A5.pdf"))
        assertEquals("/", PercentEncoding.decodeStrict("%2F"))
        assertEquals("", PercentEncoding.decodeStrict(""))
    }

    @Test
    fun malformedEscapesFallBackToLiteralSource() {
        // 不足两位十六进制：按字面 `%` 处理，不抛（判定面仍拿到原始候选＝fail-closed）
        assertEquals("x%.exe", PercentEncoding.decodeStrict("x%.exe"))
        assertEquals("x%2.exe", PercentEncoding.decodeStrict("x%2.exe"))
        assertEquals("x%2G.exe", PercentEncoding.decodeStrict("x%2G.exe"))
        // 解得出字节但不是合法 UTF-8：原样返回，不产生 U+FFFD
        assertEquals("%FF", PercentEncoding.decodeStrict("%FF"))
    }

    @Test
    fun downloadPolicyKeepsPlusLiteralAcrossPathAndQuery() {
        // 与 Windows 侧 `Uri.UnescapeDataString`（严格、不动 `+`）合一：
        // `/a+b%2Eexe` 两端解出同一个 `a+b.exe` 并都判危险。
        assertTrue(DownloadPolicy.isHardBlocked("https://c.d/a+b%2Eexe"))
        // `x.exe+` 的字面扩展名是 `exe+`——不在危险集，两端同判。旧 Android 写法先
        // 把它解成 `x.exe ` 再被净化 trim 掉空格，才比 Windows 多拦这一层。
        assertFalse(DownloadPolicy.isHardBlocked("https://c.d/x.exe+"))
        assertFalse(DownloadPolicy.requiresExplicitConfirmation("https://c.d/dl?f=x.exe+"))
        assertTrue(DownloadPolicy.requiresExplicitConfirmation("https://c.d/dl?f=%E6%8A%A5.exe"))
    }

    @Test
    fun noSecondPercentDecoderRemainsInMainSources() {
        // 「不欢迎第二个解析器」钉成判据：主源里再出现 URLDecoder 就是把 Q9 的分歧
        // 请回来。按目录现取文件清单（不是写死三份名单）——新增模块自动在判据内。
        val sources =
            File(repoRoot(), MAIN_SOURCE_DIR)
                .walkTopDown()
                .filter { it.extension == "kt" }
                .toList()
        assertTrue("扫描面为空＝目录假设塌了，判据会恒真", sources.size >= 3)
        val offenders =
            sources
                .filter { path -> codeLines(path.readText()).any { LINE_FORBIDDEN in it } }
                .map { it.name }
        assertEquals(emptyList<String>(), offenders)
    }

    /** 剔注释（口径单源 `withoutComments()`，R9-B45 / 台账 Q59）——本批注记逐字抄着被禁写法。 */
    private fun codeLines(text: String): List<String> =
        text
            .replace("\r\n", "\n")
            .withoutComments()
            .lines()
            .map { it.trim() }

    private companion object {
        private const val MAIN_SOURCE_DIR = "android/app/src/main/java"

        private const val LINE_FORBIDDEN = "URLDecoder"
    }
}

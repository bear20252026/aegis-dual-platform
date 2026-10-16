package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * R9-B80：把 §3.79 第 3 点登记的那个空档（「往桥的受信名单加第二个壳页」当时只有一行
 * KDoc 提醒、没有任何用例会红）升级成常驻锚。
 *
 * 为什么这两条都属于安全判据而不是形状洁癖：`@JavascriptInterface` 注入的对象对该
 * WebView 的**全部帧**可见，而 `isTrustedShellPage()` 只读顶层 URL（`webView.getUrl`）。
 * 于是「几个文档被当成受信」直接决定信任边界有多宽——§3.26 之前是整个
 * `file:///android_asset/` 前缀，而那句「实测壳页零 iframe ⇒ 今日无落点」正是被这个
 * 前缀判错的语料（GeoGebra 页当时受信，它的 bundle 确实拼 `<iframe …>`，见 §3.79 第 2 点）。
 * 名单今日只有 `HOME_URL` 一元；加第二元就是把刚关闭的那条通道重新打开，必须先做
 * origin-scoped 传输。本文件让这个动作**改一行就变红**，不靠下一个人记得读注释。
 */
class BridgeTrustListGuardTest {
    private fun repoRoot(): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val current = dir
            if (current != null && File(current, SHELL_DIR).isDirectory) {
                return current
            }
            dir = dir?.parentFile
        }
        error("未找到 $SHELL_DIR（请在仓库内运行测试）")
    }

    private fun read(relative: String): String {
        val file = File(repoRoot(), relative)
        assertTrue("锚的语料缺失：$relative", file.isFile)
        return file.readText()
    }

    /**
     * 剔注释后的代码文本。JS/Kotlin 走 `withoutComments()`（口径单源，R9-B45）；
     * HTML 的 `<!-- -->` 不在那个口径里，就地补一次——壳页说明段（start.html:23）
     * 逐字写着 `AegisBridge`，不剔就会被算成"消费者"，那正是本仓第五次撞的假红形态。
     */
    private fun codeOnly(relative: String): String {
        val text = read(relative)
        val withoutHtmlComments =
            if (relative.endsWith(".html")) {
                text.replace(Regex("<!--[\\s\\S]*?-->"), "")
            } else {
                text
            }
        return withoutHtmlComments.replace("\r\n", "\n").withoutComments()
    }

    @Test
    fun trustedShellPageListIsSinglyDerivedFromHomeUrl() {
        val code = codeOnly(BRIDGE_SOURCE)
        val marker = "private val TRUSTED_SHELL_PAGES ="
        val start = code.indexOf(marker)
        assertTrue(
            "语料漂移：$BRIDGE_SOURCE 里找不到「$marker」——名单不再是就地字面量，" +
                "本锚得被显式改写，不能静默空转",
            start >= 0,
        )
        val args = argumentsOf(code, "setOf(", start)
        assertEquals(
            "桥的受信名单必须只有一元。加第二个受信页＝重启 §五 Q10（R9-AD-10 / §3.79）：" +
                "@JavascriptInterface 对全部帧可见而判据只读顶层 URL，先把桥传输迁到 " +
                "origin-scoped addWebMessageListener 再谈放宽",
            1,
            args.size,
        )
        assertTrue(
            "那一元必须由 BrowserEngine.HOME_URL 派生（另抄字面量＝首页改名时两处静默失配）：$args",
            args.single().contains("BrowserEngine.HOME_URL"),
        )
    }

    @Test
    fun onlyTheHomeAdapterConsumesTheBridge() {
        val consumers = shellDocuments()
            .filter { it.second.contains("AegisBridge") }
            .map { it.first }
            .toSet()
        assertEquals(
            "壳页语料里对 AegisBridge 的代码级引用只允许出现在首页适配层 start.js。" +
                "第二个文档开始消费桥就必须进受信名单＝重启 §五 Q10（先迁 origin-scoped 传输）",
            setOf("start.js"),
            consumers,
        )
        // 正向控制：判据不能靠"什么都没匹配到"通过——真引用确实还在，注释里的说明文字
        // 确实已被剔掉（start.html:23 与 start.js:5 两处逐字写着 AegisBridge）。
        assertTrue(
            "start.js 剔注释后应仍含 window.AegisBridge 取用点",
            codeOnly("$SHELL_DIR/start.js").contains("window.AegisBridge"),
        )
        assertFalse(
            "start.html 的 AegisBridge 只出现在注释里；这里为真说明 HTML 注释剔除了",
            codeOnly("$SHELL_DIR/start.html").contains("AegisBridge"),
        )
    }

    /** shared/shell 顶层的 (文件名, 剔注释代码文本)，按名排序保证失败信息可复现。 */
    private fun shellDocuments(): List<Pair<String, String>> =
        File(repoRoot(), SHELL_DIR)
            .listFiles()
            .orEmpty()
            .filter { it.isFile && it.extension in FRONTEND_EXTENSIONS }
            .sortedBy { it.name }
            .map { it.name to codeOnly("$SHELL_DIR/${it.name}") }

    /** 取 `from` 之后第一个 [open] 调用括号内的顶层实参（嵌套括号里的逗号不切；
     *  实参字符串本身不得含逗号——语料里没有这种形态，含了会让本锚多切一段而不是少切）。 */
    private fun argumentsOf(text: String, open: String, from: Int): List<String> {
        val begin = text.indexOf(open, from)
        assertTrue("找不到 $open（名单写法已漂移）", begin >= 0)
        var depth = 1
        var end = -1
        for (index in (begin + open.length) until text.length) {
            depth += when (text[index]) {
                '(' -> 1
                ')' -> -1
                else -> 0
            }
            if (depth == 0) {
                end = index
                break
            }
        }
        assertTrue("$open 的括号未闭合", end > begin + open.length)
        val inner = text.substring(begin + open.length, end)
        return splitTopLevel(inner).filter { it.isNotBlank() }
    }

    private fun splitTopLevel(inner: String): List<String> {
        val parts = mutableListOf<String>()
        var depth = 0
        var start = 0
        inner.forEachIndexed { index, ch ->
            when (ch) {
                '(' -> depth++
                ')' -> depth--
                ',' -> if (depth == 0) {
                    parts += inner.substring(start, index).trim()
                    start = index + 1
                }
            }
        }
        parts += inner.substring(start).trim()
        return parts
    }

    private companion object {
        private const val SHELL_DIR = "shared/shell"
        private const val BRIDGE_SOURCE = "android/app/src/main/java/com/aegis/browser/AegisHomeBridge.kt"
        private val FRONTEND_EXTENSIONS = setOf("html", "js")
    }
}

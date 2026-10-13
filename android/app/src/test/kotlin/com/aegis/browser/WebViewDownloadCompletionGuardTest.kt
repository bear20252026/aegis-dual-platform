package com.aegis.browser

import android.app.DownloadManager
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import javax.xml.parsers.DocumentBuilderFactory

/**
 * R9-AD-3（队列 Q3）：下载完成后的**最终地址**复判。
 *
 * 判据面（1–5）在 JVM 里真跑；接线面（6–8）钉的是「机制建了没接线」这一类——
 * receiver 只有在 manifest 里被声明、且只以 `exported="false"` 声明，这条复判才既成立
 * 又不给任意应用伪造 download_id 的口子。三件事本仓**无设备实证**：广播的实际投递、
 * `COLUMN_URI` 是否真被 DownloadProvider 改写成跳转目标、`remove()` 是否真删掉
 * 公共目录里那个文件 ⇒ 验收步已写进 `docs/runbooks/device-validation.md` Android 第 8 步。
 */
class WebViewDownloadCompletionGuardTest {
    private val metadataLanding = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"

    // ---------------------------------------------------------------- 判据面
    @Test
    fun redirectLandingOnCloudMetadataIsRetired() {
        val rejection = WebViewDownloadCompletionGuard.verdict(metadataLanding, "http")
        assertNotNull("302 落到链路本地元数据必须命中复判", rejection)
        assertTrue(
            "留痕必须带段表拒绝码（与入队侧同源，便于跨端对账）",
            rejection!!.first.contains(com.aegis.broker.ReservedAddressBoundary.DENY_CODE),
        )
    }

    @Test
    fun loopbackLanAndCgnatLandingsStayDownloadable() {
        // B8 裁决「本机与内网必须能打开」在下载落点上的对偶锚：不得因为这是
        // 「重定向后的地址」就反向收紧——收紧会打死本地/内网下载。
        val keep =
            listOf(
                "http://127.0.0.1:8000/app.bin",
                "http://192.168.1.10/share.bin",
                "http://localhost/x",
                "http://100.100.100.200/latest/meta-data/",
            )
        for (url in keep) {
            assertNull("$url 不该被复判撤销", WebViewDownloadCompletionGuard.verdict(url, "http"))
        }
    }

    @Test
    fun rejudgeUsesTheEnqueueGateVerbatim() {
        // 「不造第二个判据源」这条要求本身要可判：同一批 URL 上复判结果必须与入队闸门
        // 逐字一致（含放行支）。哪天有人给复判另写一份段表判定，这里就红。
        val battery =
            listOf(
                metadataLanding to "http",
                "http://[::1]:9000/x" to "http",
                "http://198.18.0.1/y" to "http",
                "https://ok.example/a.bin" to "https",
                "http://239.1.1.1/m" to "http",
                "https://ok.example/a?b=1" to "https",
            )
        for ((url, scheme) in battery) {
            assertEquals(
                "复判与入队闸门必须同判：$url",
                WebViewDownloadTargetGuard.rejectionOf(url, scheme),
                WebViewDownloadCompletionGuard.verdict(url, scheme),
            )
        }
    }

    @Test
    fun unjudgeableRowsKeepTheFile() {
        // 读不到最终 URI ⇒ 不删：删不可逆，而此时判据没有任何可看的输入。
        assertNull(WebViewDownloadCompletionGuard.verdict(null, null))
        assertNull(WebViewDownloadCompletionGuard.verdict("", "http"))
        assertNull(WebViewDownloadCompletionGuard.verdict("   ", "http"))
        // 状态缺失/非成功 ⇒ 不复判，也不弹「已拦截」这种与实际不符的话。
        assertNull(WebViewDownloadCompletionGuard.rowVerdict(null, metadataLanding, "http"))
        assertNull(WebViewDownloadCompletionGuard.rowVerdict(2, metadataLanding, "http"))
    }

    @Test
    fun schemelessLandingIsNotExempted() {
        // 与上一条相反的分支要有名字：URI 读到了但取不出 scheme（畸形/前缀被截）时
        // **不豁免**——入队闸门对同样的输入就判「非 http(s) 拦」，复判在这里改成放行
        // 就是第二套口径，而「落点看不出问题就先留着」等于把拦不住说成已处理。
        assertNotNull(WebViewDownloadCompletionGuard.verdict("169.254.169.254/latest", null))
        assertEquals(
            "必须与入队闸门同判",
            WebViewDownloadTargetGuard.rejectionOf("169.254.169.254/latest", null),
            WebViewDownloadCompletionGuard.verdict("169.254.169.254/latest", null),
        )
    }

    @Test
    fun rowVerdictJudgesStatusBeforeAddress() {
        assertNotNull(
            "成功完成 + 落点命中 ⇒ 必须撤销",
            WebViewDownloadCompletionGuard.rowVerdict(DOWNLOAD_STATUS_SUCCESSFUL, metadataLanding, "http"),
        )
        // 同一条 metadataLanding，状态换成 pending 就不动——顺序即优先级。
        assertNull(WebViewDownloadCompletionGuard.rowVerdict(1, metadataLanding, "http"))
        assertTrue(WebViewDownloadCompletionGuard.shouldRejudge(DownloadManager.STATUS_SUCCESSFUL))
        assertEquals(DownloadManager.STATUS_SUCCESSFUL, DOWNLOAD_STATUS_SUCCESSFUL)
    }

    // ---------------------------------------------------------------- 接线面
    @Test
    fun receiverIsDeclaredAndNotExported() {
        val manifest = parse(mainDir().resolve("AndroidManifest.xml"))
        val receivers = manifest.getElementsByTagName("receiver")
        assertEquals("manifest 里的 receiver 只该有下载完成复判这一个", 1, receivers.length)
        val receiver = receivers.item(0) as Element
        assertEquals(
            "必须指向复判 receiver（改了类名不改 manifest＝机制建了没接线）",
            ".WebViewDownloadCompletionReceiver",
            receiver.getAttribute("android:name"),
        )
        assertEquals(
            "exported 必须 false：这条广播由系统按归属定投，导出去等于让任意应用伪造 download_id 触发我们的删除",
            "false",
            receiver.getAttribute("android:exported"),
        )
        // 只看 receiver 自己那棵子树——manifest 里 activity 也带 <action>，
        // 按文档级 getElementsByTagName("action") 数会把它的一起算进来（实测 3 个）。
        val actions = receiver.getElementsByTagName("action")
        assertEquals(1, actions.length)
        assertEquals(
            "intent-filter 只认 DOWNLOAD_COMPLETE",
            "android.intent.action.DOWNLOAD_COMPLETE",
            (actions.item(0) as Element).getAttribute("android:name"),
        )
    }

    @Test
    fun receiverWiringReadsTheLandingColumnAndRemovesTheFile() {
        val text = mainDir().resolve("java/com/aegis/browser/WebViewDownloadCompletionReceiver.kt").toFile().readText()
        assertTrue(text.contains("intent?.action != DownloadManager.ACTION_DOWNLOAD_COMPLETE"))
        assertTrue(text.contains("DownloadManager.COLUMN_URI"))
        assertTrue(text.contains("WebViewDownloadCompletionGuard.rowVerdict("))
        assertTrue(text.contains("manager.remove(downloadId)"))
        // 撤销失败要单独留痕——那种输入下文件仍在公共目录，Toast 说「已拦截」就是假话。
        assertTrue(text.contains("复判命中但撤销下载失败"))
    }

    @Test
    fun onlyTheSharedGateJudgesDownloadTargets() {
        // 全 app main 源面里 `rejectionOf(` 只允许两个出处：闸门自身、以及新增的完成复判。
        // 第三处出现＝第二个判据源（本仓反复登记的「各抄一份」）。
        val sources = File(System.getProperty("user.dir"), "src/main/java")
        val callers =
            sources
                .walkTopDown()
                .filter { it.isFile && it.extension == "kt" }
                .filter { "rejectionOf(" in it.readText() }
                .map { it.name }
                .sorted()
                .toList()
        assertEquals(
            "地址判据只能有这两个出处：$callers",
            listOf("WebViewDownloadCompletionGuard.kt", "WebViewDownloadTargetGuard.kt"),
            callers,
        )
        // 入队侧那道闸门仍在原地——复判是补洞，不是替代。
        val handler = mainDir().resolve("java/com/aegis/browser/WebViewDownloadHandler.kt").toFile().readText()
        assertTrue(handler.contains("WebViewDownloadTargetGuard.interceptIfRejected("))
    }

    private fun parse(file: Path): org.w3c.dom.Document {
        val factory = DocumentBuilderFactory.newInstance()
        return factory.newDocumentBuilder().parse(file.toFile())
    }

    /** 仓库内 android/app/src/main（与 NetworkSecurityConfigGuardTest 同法定位）。 */
    private fun mainDir(): Path =
        generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
            .take(8)
            .map { it.resolve("src").resolve("main") }
            .firstOrNull { Files.isRegularFile(it.resolve("AndroidManifest.xml")) }
            ?: error("未找到 app/src/main（请在仓库内运行测试）")
}

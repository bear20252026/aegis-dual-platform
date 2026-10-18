package com.aegis.browser

import com.aegis.broker.ThreatHostFeed
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * 内置威胁名单装载面的判据（R9-B95 / 队列 Q51 的机制半边）。
 *
 * 这里刻意**不起 Robolectric**：AssetManager 那一层只有「按给定路径读出文本」这一件事，
 * 真正会出错的是路径常量与磁盘上的文件各说各话、以及「名单里其实混着死条目」。
 * 因此判据落在两处可核对的事实上：代码里的 asset 路径 ⇄ 仓库里真实存在的文件；
 * 那份文件的文本 ⇄ 解析结果。
 */
class BuiltInThreatHostsTest {
    private val assetFile: File by lazy { repoFile(ASSET_UNDER_ROOT) }

    @Test
    fun theAssetPathConstantPointsAtAFileThatIsActuallyPackaged() {
        // 代码写着 threat/hosts.txt、磁盘上是别的名字 ⇒ APK 里没有这份名单，
        // 而装载链会安静地报 built_in_feed_unavailable。这条锚就是为了让那种漂移当场红。
        assertEquals(THREAT_ASSET_PATH, ThreatHostFeed.BUILT_IN_ASSET_PATH)
        assertTrue("内置名单文件不在仓库里：$assetFile", assetFile.isFile)
    }

    @Test
    fun shippingBuiltInListIsEmptyByDecisionNotByAccident() {
        val parsed = ThreatHostFeed.parse(assetFile.readText())
        assertEquals(
            "出厂内置名单不再是空的——「内置哪份名单」属发布决定（台账 §4.0 表 D3），" +
                "补内容必须与所有者决定同批，并一并写明来源与许可",
            emptyList<String>(),
            parsed.hosts,
        )
        assertEquals("头注里每一行都必须是注释；被拒条目说明格式与解析口径漂了", 0, parsed.rejected.size)
    }

    @Test
    fun theLoaderConsumesTheRealFileThroughTheSharedParser() {
        // 装载链的端到端形状：读文本 → 解析 → 切批。空清单也要出一批（Published(0/0) 的判据
        // 由 :broker 侧的 CoreDenylistPushTest 钉），这里核的是「真文件不会把链卡住」。
        val parsed = ThreatHostFeed.parse(assetFile.readText())
        val plan = ThreatHostFeed.batches(parsed.hosts)
        assertEquals(1, plan.size)
        assertEquals(0, plan.single().size)
    }

    @Test
    fun aNonEmptyListWouldReachTheCoreThroughTheSamePath() {
        // 反面对照：把「将来给出名单内容」那一天的形状先在纯逻辑层跑通——
        // 非空清单出多批时，装载链不需要再改任何代码。
        val text =
            buildString {
                append("# 模拟所有者给出的名单\n")
                repeat(4_000) { index -> append("||host$index.example^\n") }
            }
        val parsed = ThreatHostFeed.parse(text)
        assertEquals(4_000, parsed.hosts.size)
        assertTrue(ThreatHostFeed.batches(parsed.hosts).size > 1)
    }

    @Test
    fun theLoaderIsWiredIntoTheExistingPrewarmThread() {
        // 「机制建了但没人接线」是这个仓反复记过的失效形态：删掉 AegisApplication 里那一行，
        // 上面四条用例全都还绿，而名单装载静默消失。这条锚判的是**调用点存在于代码里**，
        // 所以剔注释是必须的（注释里写着同一个调用形态时不许算命中）。
        val source = repoFile(AEGIS_APPLICATION_UNDER_ROOT).readText().withoutComments()
        assertTrue("AegisApplication 不再调用内置名单装载（$CALL）——链在但没人踩", source.contains(CALL))
        assertEquals("装载调用只能有一处", 1L, occurrences(source, CALL).toLong())
    }

    @Test
    fun theWiringAnchorCanFail() {
        // 正面控制：同一个计数面在「只有注释里有」时必须 0、在「真调用」时必须 1——
        // 没有这一条，上面那条断言在一个被注释掉的接线上也绿。
        val commentedOnly = "        // $CALL\n        broker.toString()\n"
        assertEquals(0L, occurrences(commentedOnly.withoutComments(), CALL).toLong())
        assertEquals(1L, occurrences("Thread({ $CALL })", CALL).toLong())
    }

    private fun occurrences(
        text: String,
        needle: String,
    ): Int = text.split(needle).size - 1

    private fun repoFile(relative: String): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
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
        const val THREAT_ASSET_PATH = "threat/hosts.txt"
        const val ASSET_UNDER_ROOT = "android/app/src/main/assets/threat/hosts.txt"
        const val AEGIS_APPLICATION_UNDER_ROOT = "android/app/src/main/java/com/aegis/browser/AegisApplication.kt"
        const val CALL = "BuiltInThreatHosts.publish(this, broker)"
    }
}

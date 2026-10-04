package com.aegis.browser

import android.app.Application
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * WebViewVersionCheck 单测。isOutdated 阈值边界（2026-09-24 审计——AD-030）：
 * 阈值 = 132_000_000（CVE-2026-12438/11295 防御线——随安全公告维护）；
 * AD-218（2026-09-26 审计）：versionCode 改 longVersionCode（Long）——
 * 阈值断言同步 Long 口径。
 *
 * AD-204（审计 2026-09-23 清单·A7 批）：openUpdate 双跳转链路（market:// →
 * https 兜底）+ 受理结果 Boolean——跳转动作经注入接缝离线驱动（原实现
 * 双跳全静默吞掉，失败面零测试）。类挂 Robolectric（候选 Intent 构造需要
 * 真实 Uri 解析）。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WebViewVersionCheckTest {
    // R7-AD-01（第七轮 2026-10-04）：阈值改**版本名**口径。旧实现把 132_000_000
    // 直接与 longVersionCode 比较，而真实 ASW 的 longVersionCode 是十位量级
    // （同仓 ProviderTest 用 141_000_7390L 表示 141.0.7390.0）——于是任何能跑
    // minSdk 26 的设备都恒判"版本安全"，CVE-2026-12438/11295 提示静默为零。

    private fun version(
        name: String,
        code: Long = 0L,
    ) = WebViewVersionCheck.WebViewVersion(name, code)

    @Test
    fun belowSafeMajorIsOutdated() {
        assertTrue(WebViewVersionCheck.isOutdated(version("131.0.6778.135")))
        assertTrue(WebViewVersionCheck.isOutdated(version("118.0.1997.106")))
        assertTrue(WebViewVersionCheck.isOutdated(version("40.0.2214.89")))
    }

    @Test
    fun atOrAboveSafeMajorIsNotOutdated() {
        assertFalse(WebViewVersionCheck.isOutdated(version("132.0.6834.163")))
        assertFalse(WebViewVersionCheck.isOutdated(version("141.0.7390.0")))
        assertFalse(WebViewVersionCheck.isOutdated(version("150.0.7871.124")))
    }

    @Test
    fun unparsableNameFailsClosedToWarning() {
        // 判不了就提示——绝不因为"读不懂版本名"而静默宣布安全
        assertTrue(WebViewVersionCheck.isOutdated(version("unknown")))
        assertTrue(WebViewVersionCheck.isOutdated(version("")))
        assertTrue(WebViewVersionCheck.isOutdated(version("beta-nightly")))
        assertTrue(WebViewVersionCheck.isOutdated(version("141")))
    }

    @Test
    fun suffixAndVendorFormsParse() {
        assertEquals(141 to 7390, WebViewVersionCheck.parseVersion("141.0.7390.163"))
        assertEquals(141 to 7390, WebViewVersionCheck.parseVersion("141.0.7390.163-bugfix"))
        assertEquals(132 to 0, WebViewVersionCheck.parseVersion("132.0"))
        assertNull(WebViewVersionCheck.parseVersion("141"))
        assertNull(WebViewVersionCheck.parseVersion("not.a.version"))
    }

    @Test
    fun decisionNeverReadsVersionCode() {
        // 判定必须取版本名：给一个"十位 longVersionCode + 过旧版本名"的组合，
        // 仍须判过旧——旧实现正是被编码量级骗过（阈值 1.32×10⁸ vs 编码 10 位）
        assertTrue(WebViewVersionCheck.isOutdated(version("118.0.1997.106", code = 1_180_199_710L)))
        assertFalse(WebViewVersionCheck.isOutdated(version("141.0.7390.0", code = 1_410_007_390L)))
    }

    // ---------------- AD-204（审计 2026-09-23 清单·A7 批）：双跳转受理结果 ----------------

    @Test
    fun openUpdateReturnsTrueWhenFirstCandidateStarts() {
        // market:// 候选可用（有 Play Store 的设备）——返回 true，且只发起一次
        val started = mutableListOf<Intent>()
        val context = ApplicationProvider.getApplicationContext<Application>()
        assertTrue(
            WebViewVersionCheck.openUpdate(context) { intent ->
                started.add(intent)
            },
        )
        assertEquals(1, started.size)
    }

    @Test
    fun openUpdateFallsBackToSecondCandidateWhenFirstThrows() {
        // 第一跳（market://）ActivityNotFound → 第二跳（https web 兜底）成功
        val started = mutableListOf<Intent>()
        val context = ApplicationProvider.getApplicationContext<Application>()
        assertTrue(
            WebViewVersionCheck.openUpdate(context) { intent ->
                if (started.isEmpty()) {
                    started.add(intent)
                    throw android.content.ActivityNotFoundException("no market app")
                }
                started.add(intent)
            },
        )
        assertEquals("两级候选都必须被尝试", 2, started.size)
    }

    @Test
    fun openUpdateReturnsFalseWhenAllCandidatesThrow() {
        // 无商店且无浏览器（双跳全失败）→ 返回 false 供调用方降级提示
        // （原实现静默吞掉——点「去更新」毫无反馈）
        val context = ApplicationProvider.getApplicationContext<Application>()
        var attempts = 0
        assertFalse(
            WebViewVersionCheck.openUpdate(context) { _ ->
                attempts += 1
                throw android.content.ActivityNotFoundException("no resolver at all")
            },
        )
        assertEquals("失败前必须穷尽全部候选（不得提前放弃）", 2, attempts)
    }

    @Test
    fun openUpdateTreatsSecurityExceptionAsCandidateFailure() {
        val context = ApplicationProvider.getApplicationContext<Application>()
        assertFalse(
            WebViewVersionCheck.openUpdate(context) { _ ->
                throw SecurityException("blocked by policy")
            },
        )
    }

    @Test
    fun updateIntentsAreMarketFirstThenWebFallback() {
        // AD-205：双跳转链路抽纯函数单源——次序即契约：Play Store 详情页
        // （market://）优先，Web 页面兜底；目标包名必须锁定 WebView 提供方
        val intents = WebViewVersionCheck.updateIntents()
        assertEquals(2, intents.size)
        assertEquals("market://details?id=com.google.android.webview", intents[0].data.toString())
        assertEquals(
            "https://play.google.com/store/apps/details?id=com.google.android.webview",
            intents[1].data.toString(),
        )
        assertEquals(Intent.ACTION_VIEW, intents[0].action)
    }
}

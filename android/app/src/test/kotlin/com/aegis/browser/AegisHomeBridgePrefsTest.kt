package com.aegis.browser

import android.content.Context
import android.webkit.WebView
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mockito.mock
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.mockito.Mockito.`when` as whenever

/**
 * AD-113/114（审计 2026-09-23 清单·A6 批）：AegisHomeBridge 偏好写入拒绝面
 * Robolectric 单测——setWallpaper 非白名单拒绝、setEngine 非法 key 拒绝、
 * 非受信壳页调用一律拒绝（桥的安全边界是「白名单值 + 受信页面」双闸）。
 * SharedPreferences 需要 Robolectric 真实实现（纯 JVM 桩返回 null）。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AegisHomeBridgePrefsTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    /** 受信壳页宿主（getUrl 桩为 assets 首页）。 */
    private val trustedWebView: WebView =
        mock(WebView::class.java).also { whenever(it.url).thenReturn("file:///android_asset/start.html") }

    private fun bridge(provider: () -> WebView?) = AegisHomeBridge(context, provider)

    private fun stored(key: String): String? =
        context
            .getSharedPreferences(SearchEngines.PREFS_NAME, Context.MODE_PRIVATE)
            .getString(key, null)

    // ---------------------------------------------------------------- AD-114

    @Test
    fun setEngineSavesWhitelistedKey() {
        bridge { trustedWebView }.setEngine("bing")
        assertEquals("bing", stored(SearchEngines.KEY_ENGINE))
    }

    @Test
    fun setEngineRejectsUnknownKey() {
        bridge { trustedWebView }.setEngine("duckduckgo")
        bridge { trustedWebView }.setEngine("")
        bridge { trustedWebView }.setEngine("baidu; drop table")
        assertNull("非法 key 不得写入偏好", stored(SearchEngines.KEY_ENGINE))
    }

    // ---------------------------------------------------------------- AD-113

    @Test
    fun setWallpaperSavesWhitelistedName() {
        bridge { trustedWebView }.setWallpaper("aurora-lime.jpg")
        assertEquals("aurora-lime.jpg", stored("wallpaper"))
    }

    @Test
    fun setWallpaperRejectsNonWhitelistedName() {
        bridge { trustedWebView }.setWallpaper("evil.jpg")
        bridge { trustedWebView }.setWallpaper("../../system/build.prop")
        bridge { trustedWebView }.setWallpaper("")
        assertNull("白名单外名称不得写入偏好", stored("wallpaper"))
    }

    // ---------------------------------------------- 双闸：非受信壳页一律拒绝

    @Test
    fun callsFromRemotePageAreRejectedBeforeWhitelist() {
        // 即使 key/名称在白名单内，非受信壳页的调用也必须整单拒绝
        val remoteWebView: WebView =
            mock(WebView::class.java).also {
                whenever(it.url).thenReturn("https://evil.example/phish")
            }
        bridge { remoteWebView }.setEngine("baidu")
        bridge { remoteWebView }.setWallpaper("aurora-lime.jpg")
        assertNull(stored(SearchEngines.KEY_ENGINE))
        assertNull(stored("wallpaper"))
    }

    @Test
    fun nullProviderFailsClosed() {
        bridge { null }.setEngine("baidu")
        assertNull(stored(SearchEngines.KEY_ENGINE))
    }

    // --------------------------------------------------------- getWallpaper

    @Test
    fun getWallpaperRoundTripsStoredValue() {
        val b = bridge { trustedWebView }
        assertEquals("", b.getWallpaper())
        b.setWallpaper("aurora-violet.jpg")
        assertEquals("aurora-violet.jpg", b.getWallpaper())
    }

    // --------------------------------------------------- AD-112：纯判定函数

    @Test
    fun trustedShellUrlPureJudge() {
        assertTrue(AegisHomeBridge.isTrustedShellUrl("about:blank"))
        assertTrue(AegisHomeBridge.isTrustedShellUrl("file:///android_asset/start.html"))
        assertTrue(
            AegisHomeBridge.isTrustedShellUrl("file:///android_asset/geogebra/GeoGebra/HTML5/5.0/GeoGebra.html"),
        )
        // 远端页面 / 本地文件旁路 / 空值一律不受信（fail-closed）
        assertFalse(AegisHomeBridge.isTrustedShellUrl("https://evil.example/phish"))
        assertFalse(AegisHomeBridge.isTrustedShellUrl("file:///sdcard/evil.html"))
        assertFalse(AegisHomeBridge.isTrustedShellUrl("file://attacker/android_asset/start.html"))
        assertFalse(AegisHomeBridge.isTrustedShellUrl(null))
        assertFalse(AegisHomeBridge.isTrustedShellUrl(""))
    }
}

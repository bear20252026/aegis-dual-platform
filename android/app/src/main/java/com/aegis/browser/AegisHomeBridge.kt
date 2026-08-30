package com.aegis.browser

import android.content.Context
import android.webkit.JavascriptInterface
import android.webkit.WebView

/**
 * 首页宿主桥（shared/shell/start.html 的 Android 侧能力面——ADR-007 单源首页）。
 *
 * 暴露能力（与 Windows pywebview 侧对齐的子集）：
 * - navigate(input)：地址栏/搜索框跳转——经 SecureNavigator.navigateExternal
 *   完整安全策略（normalizeExternal + Broker 授权），非旁路；
 * - setEngine/getEngine：搜索引擎选择（SharedPreferences 持久化）；
 * - setWallpaper/getWallpaper：首页壁纸选择（SharedPreferences 持久化）；
 * - openGeogebra()：离线几何画板（assets 内置资源，file:///android_asset 加载）；
 * - logError(message)：首页 JS 异常上报（Log.e 留痕）。
 *
 * 安全口径（ADR-003 复审）：addJavascriptInterface 对所有页面可见——
 * 本桥仅暴露「无数据读取、无状态篡改」的入口级操作（与 Windows 端
 * 标签结构操作放行同口径）；壁纸/引擎偏好写入仅限白名单值。
 */
class AegisHomeBridge(
    private val context: Context,
    private val webViewProvider: () -> WebView?,
) {
    private val prefs = context.getSharedPreferences("aegis_home", Context.MODE_PRIVATE)

    companion object {
        private val ENGINE_URLS = mapOf(
            "baidu" to "https://www.baidu.com/s?wd=",
            "bing" to "https://www.bing.com/search?q=",
            "google" to "https://www.google.com/search?q=",
            "sogou" to "https://www.sogou.com/web?query=",
        )
        private const val DEFAULT_ENGINE = "baidu"

        /** 首页壁纸白名单（与 shared/shell/wallpapers 文件一一对应）。 */
        private val WALLPAPERS = setOf(
            "aurora-magenta.jpg", "aurora-lime.jpg",
            "aurora-twilight.jpg", "aurora-violet.jpg",
        )
    }

    @JavascriptInterface
    fun logError(message: String) {
        android.util.Log.e("AegisHome", message ?: "")
    }

    @JavascriptInterface
    fun setEngine(key: String) {
        if (ENGINE_URLS.containsKey(key)) {
            prefs.edit().putString("engine", key).apply()
        }
    }

    @JavascriptInterface
    fun getEngine(): String = prefs.getString("engine", DEFAULT_ENGINE) ?: DEFAULT_ENGINE

    @JavascriptInterface
    fun setWallpaper(name: String) {
        if (name in WALLPAPERS) {
            prefs.edit().putString("wallpaper", name).apply()
        }
    }

    @JavascriptInterface
    fun getWallpaper(): String = prefs.getString("wallpaper", "") ?: ""

    /** 首页搜索/地址栏跳转：搜索词拼引擎 URL，网址走白名单校验后导航。 */
    @JavascriptInterface
    fun navigate(input: String) {
        val text = input?.trim().orEmpty()
        if (text.isEmpty()) return
        val url = buildTargetUrl(text) ?: return
        val wv = webViewProvider() ?: return
        SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(url)
    }

    /** 打开离线几何画板（assets 内置资源——build.gradle sourceSets 打包）。 */
    @JavascriptInterface
    fun openGeogebra(): Boolean {
        val wv = webViewProvider() ?: return false
        wv.post {
            wv.loadUrl("file:///android_asset/geogebra/GeoGebra/HTML5/5.0/GeoGebra.html")
        }
        return true
    }

    private fun buildTargetUrl(text: String): String? {
        val looksLikeUrl = !text.contains(" ") && text.contains(".") &&
            !text.endsWith(".")
        return if (looksLikeUrl) {
            "https://$text"
        } else {
            val engine = ENGINE_URLS[getEngine()] ?: ENGINE_URLS[DEFAULT_ENGINE]!!
            engine + android.net.Uri.encode(text)
        }
    }
}

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
 * - openGeogebra()：离线几何画板（经导航器 openTrustedAsset 常量白名单加载）；
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
    private val prefs = context.getSharedPreferences(SearchEngines.PREFS_NAME, Context.MODE_PRIVATE)

    companion object {
        /** 引擎显示名（P1-2：与 Windows SEARCH_ENGINES 中文名对齐）。 */
        private val ENGINE_NAMES = mapOf("baidu" to "百度", "bing" to "必应", "google" to "谷歌", "sogou" to "搜狗")

        /** 首页壁纸白名单（与 shared/shell/wallpapers 文件一一对应）。 */
        private val WALLPAPERS =
            setOf(
                "aurora-magenta.jpg",
                "aurora-lime.jpg",
                "aurora-twilight.jpg",
                "aurora-violet.jpg",
            )
    }

    @JavascriptInterface
    fun logError(message: String) {
        android.util.Log.e("AegisHome", message ?: "")
    }

    @JavascriptInterface
    fun setEngine(key: String) {
        if (SearchEngines.ENGINE_URLS.containsKey(key)) {
            prefs.edit().putString(SearchEngines.KEY_ENGINE, key).apply()
        }
    }

    /**
     * P1-2 修复（搜索审计 2026-09-01）：返回 JSON 对象字符串，与 Windows
     * `get_search_engine()` 同构——`{"engine":"baidu","engines":[{"key","name"}]}`。
     * 旧实现只返回引擎 key 字符串，start.html 期望对象结构 → `ENGINES=[]`
     * → 引擎 pill 永远显示初始"百度"且点击无响应（cycleEngine 直接 return）。
     */
    @JavascriptInterface
    fun getEngine(): String {
        val current = prefs.getString(SearchEngines.KEY_ENGINE, null) ?: SearchEngines.DEFAULT_ENGINE
        val engines =
            org.json.JSONArray().apply {
                SearchEngines.ENGINE_URLS.keys.forEach { key ->
                    put(
                        org.json.JSONObject().apply {
                            put("key", key)
                            put("name", ENGINE_NAMES[key] ?: key)
                        },
                    )
                }
            }
        return org.json
            .JSONObject()
            .put("engine", current)
            .put("engines", engines)
            .toString()
    }

    @JavascriptInterface
    fun setWallpaper(name: String) {
        if (name in WALLPAPERS) {
            prefs.edit().putString("wallpaper", name).apply()
        }
    }

    @JavascriptInterface
    fun getWallpaper(): String = prefs.getString("wallpaper", "") ?: ""

    /** 首页搜索/地址栏跳转：归一走 SearchEngines 单源（搜索词/网址同语义）。 */
    @JavascriptInterface
    fun navigate(input: String) {
        val text = input?.trim().orEmpty()
        if (text.isEmpty()) return
        // P0-2/P1-1 修复（搜索审计 2026-09-01）：与地址栏共用 normalizeInput
        // 单源——旧 buildTargetUrl 会把 `https://www.baidu.com` 拼成
        // `https://https://...`（looksLikeUrl 只看含点号，不看已有 scheme）
        val url = SearchEngines.normalizeInput(text, SearchEngines.currentEngine(context)) ?: return
        val wv = webViewProvider() ?: return
        // @JavascriptInterface 运行在 JS 后台线程——WebView API 必须
        // 主线程调用（WrongThreadViolation：loadUrl 被吞 → 导航静默失效）
        // P0 修复（全量复审 2026-09-01）：失败不再静默——此前返回值被丢弃，
        // 会话过期/策略拒绝时首页搜索与地址栏跳转零反馈（用户以为点了没反应）
        wv.post {
            val ok = SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(url) == true
            if (!ok) {
                android.widget.Toast
                    .makeText(context, "无法打开：未通过安全策略验证", android.widget.Toast.LENGTH_SHORT)
                    .show()
            }
        }
    }

    /**
     * 打开离线几何画板（assets 内置资源——build.gradle sourceSets 打包）。
     * H-5 修复（审计 2026-08-31）：不再直接 wv.loadUrl——经导航器
     * openTrustedAsset 常量白名单加载，加载路径收敛到 SecureNavigator
     * 单一路径，消除桥接层 file:// 直载旁路。
     */
    @JavascriptInterface
    fun openGeogebra(): Boolean {
        val wv = webViewProvider() ?: return false
        wv.post {
            SecureWebViewFactory.navigatorFor(wv)?.openTrustedAsset(
                "geogebra/GeoGebra/HTML5/5.0/GeoGebra.html",
            )
        }
        return true
    }

    /**
     * 首页返回按钮（start.html 单源——与 Windows go_back 同名能力）：
     * 经受控导航器逐级回退 WebView 历史栈，无历史时 no-op（不退出应用）。
     */
    @JavascriptInterface
    fun goBack() {
        val wv = webViewProvider() ?: return
        wv.post {
            if (wv.canGoBack()) {
                SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(HistoryAction.BACK)
            }
        }
    }
}

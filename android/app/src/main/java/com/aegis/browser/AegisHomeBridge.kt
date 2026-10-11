package com.aegis.browser

import android.content.Context
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.Toast
import com.aegis.webviewadapter.LogRedact

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
 *
 * P1-1 修复（全面审计 2026-09-04）：注入对象对任意远端页面可见且
 * `window.AegisBridge` 存在性是指纹探针——所有 @JavascriptInterface 方法
 * 入口先经 [isTrustedShellPage] 校验：宿主 WebView 当前 URL 仅允许**壳页精确名单**
 * （`file:///android_asset/start.html`，Q50 收窄——此前是整个 assets 前缀，
 * 于是内置 GeoGebra 页也拿到桥）或 `about:blank`；远端页面
 * 调用一律拒绝执行并 Log.w 留痕（壳页调用频率低，校验无性能影响）。
 */
class AegisHomeBridge(
    private val context: Context,
    private val webViewProvider: () -> WebView?,
    // AD-323（2026-10-02 审计）：主线程投递抽可注入 executor——原 navigate 的
    // wv.post 内联使 JVM 单测无法驱动「归一→投递→导航」链（投递不可观测）。
    // 生产默认 wv.post（WebView API 必须主线程调用）；测试注入同步执行器
    // 断言归一/拒绝分支。
    private val postToMainThread: (WebView, () -> Unit) -> Unit = { wv, block -> wv.post(block) },
) {
    private val prefs = context.getSharedPreferences(SearchEngines.PREFS_NAME, Context.MODE_PRIVATE)

    companion object {
        /** 首页壁纸白名单（与 shared/shell/wallpapers 文件一一对应）。
         *  AD-147（审计 2026-09-23 清单·A6 批）：internal 化供打包校验单测——
         *  WallpaperPackagingTest 断言本表与 shared/shell/wallpapers 目录
         *  内容双向一致（人工同步的漂移在打包门禁暴露）。 */
        internal val WALLPAPERS =
            setOf(
                "aurora-magenta.jpg",
                "aurora-lime.jpg",
                "aurora-twilight.jpg",
                "aurora-violet.jpg",
            )

        /** P1-1 修复：壳页资源的共同前缀（精确名单见 TRUSTED_SHELL_PAGES）。 */
        private const val TRUSTED_SHELL_PREFIX = "file:///android_asset/"

        /**
         * Q50（第九轮 §五 R9-AD-11 / 外部第三轮审计 AX-03）：桥的受信面从「整个
         * `file:///android_asset/` 前缀」收窄成**壳页精确名单**。
         *
         * 前缀语义把内置离线 GeoGebra 页也算成受信调用者——那是一枚第三方 bundle，
         * 经 `openGeo` 顶层导航后仍能在同一个 WebView 里调 `navigate/setEngine/
         * setWallpaper/goBack/logError`。收窄的依据是实测零消费，不是猜测：
         * `dist/geogebra-cache` 当前副本 grep `AegisBridge`/`__aegis`/`android_asset`/
         * `JavascriptInterface`/`navigate(` **全 0 命中**（`openGeo` 的 3 处是 GWT 自带的
         * `OpenGeoProver` 字符串），画板页也不加载 `start.js`（后者在 assets 根的
         * `start.html`，画板在 `geogebra/` 子树），从画板返回走 `MainActivity` 原生
         * `navigateHistory(BACK)` 而非桥的 `goBack`。⇒ 主页之外没有合法桥消费者。
         *
         * 只认**顶层资源名**（不含子路径）：新增壳页必须在这里显式登记，而不是
         * 靠「它在 assets 目录下」自动获得桥。名单从 `BrowserEngine.HOME_URL` 派生
         * 而不是另抄一份字面量——URL 的第二定义源会随首页改名而静默失配
         * （`HomeUrlContractTest` 钉住 HOME_URL 本身）。
         */
        private val TRUSTED_SHELL_PAGES =
            setOf(BrowserEngine.HOME_URL.removePrefix(TRUSTED_SHELL_PREFIX))

        /** AD-235：日志净化截断上限（与 BrowserViewModel 标题净化同口径 120）。 */
        private const val LOG_MESSAGE_MAX_LENGTH = 120

        /**
         * AD-250（2026-09-26 审计）：引擎 JSON 组装 internal 化——
         * @JavascriptInterface 方法必须 public（JS 反射仅暴露 public 注解
         * 方法，无法直接 internal 化），抽取纯函数供 JVM 单测断言与
         * start.html 的消费契约：`{"engine":<key>,"engines":[{"key","name"}]}`。
         * AD-146（审计 2026-09-23 清单·A6 批）：显示名消费 SearchEngines
         * 单源（键集一致性由 SearchEnginesTest 锁定）。
         *
         * AD-191（审计 2026-09-23 清单·A7 批）：引擎数组静态缓存——引擎键集
         * 编译期固定（ENGINE_URLS 为常量表），原实现每次 getEngine 都重建
         * JSONArray（@JavascriptInterface 每次面板渲染都跨 JNI 调用）。
         * 现数组序列化结果 lazy 驻留单份，每次调用只拼当前 engine 键。
         */
        private val cachedEnginesArrayJson: String by lazy {
            val engines = org.json.JSONArray()
            SearchEngines.ENGINE_URLS.keys.forEach { key ->
                val entry = org.json.JSONObject()
                entry.put("key", key)
                entry.put("name", SearchEngines.ENGINE_NAMES[key] ?: key)
                engines.put(entry)
            }
            engines.toString()
        }

        internal fun buildEngineJson(currentEngine: String): String =
            // engine 键经 JSONObject.quote（JSON 字符串字面量转义）——prefs 值
            // 即便被写入异常字符也不会产出非法 JSON；engines 部分为静态缓存
            // 逐字节复用。
            "{\"engine\":${org.json.JSONObject.quote(currentEngine)},\"engines\":$cachedEnginesArrayJson}"

        /**
         * AD-112（审计 2026-09-23 清单·A6 批）：受信壳页 URL 判定抽纯函数——
         * 原判定内嵌在 isTrustedShellPage（依赖 WebView getUrl，不可 JVM 单测）。
         * 纯字符串判定 single 判定点：about:blank 精确匹配，或 assets 根下的
         * **壳页精确名单**成员（Q50 收窄，此前是整个前缀）。
         * 写成单个 `when` 表达式而不是四段提前 return——detekt ReturnCount 的上限是 2，
         * 而这里语义上就是「四条互斥分支」，用表达式比用一串守卫语句更贴合。
         */
        internal fun isTrustedShellUrl(url: String?): Boolean =
            when {
                url == null -> false
                url == "about:blank" -> true
                !url.startsWith(TRUSTED_SHELL_PREFIX) -> false
                else -> shellPageOf(url) in TRUSTED_SHELL_PAGES
            }

        /**
         * 剥掉 query/fragment 后的顶层资源名。这两个装饰不改变「是哪个文档」，
         * 而壳页确实可能带着 `#片段` 被 getUrl 报告回来（不剥就会把自家首页拒了）；
         * 剥完必须**逐字**等于登记名，不接受子路径。
         */
        private fun shellPageOf(url: String): String =
            url
                .removePrefix(TRUSTED_SHELL_PREFIX)
                .substringBefore('#')
                .substringBefore('?')
    }

    /**
     * P1-1 修复（全面审计 2026-09-04）：受信壳页校验（单一判定点）。宿主
     * WebView 当前 URL 仅允许壳页精确名单或 about:blank（判定逻辑单源在
     * [Companion.isTrustedShellUrl]，AD-112；名单收窄见 Q50）。@JavascriptInterface
     * 运行在 JS 后台线程，getUrl 以 runCatching 包裹——异常按拒绝处理
     * （fail-closed），不因跨线程读取崩溃放行。
     */
    private fun isTrustedShellPage(): Boolean {
        val url =
            webViewProvider()
                ?.let { wv -> runCatching { wv.url }.getOrNull() }
        val trusted = isTrustedShellUrl(url)
        if (!trusted) {
            // AD-257（2026-10-01 审计）：拒绝路径明文记录完整 URL 是脱敏口径的
            // 第三处漏接（拒绝 URL 可含 query token）——统一经 LogRedact.redact
            // （与 AegisWebViewClient/WebViewDownloadHandler 同单源）。
            android.util.Log.w("AegisHome", "[security] AegisBridge 拒绝非壳页调用: ${LogRedact.redact(url)}")
        }
        return trusted
    }

    @JavascriptInterface
    fun logError(message: String) {
        if (!isTrustedShellPage()) return
        // AD-235（2026-09-26 审计）：message 为非空 String——原 `?: ""` 是对
        // 非空类型的冗余判空（已删）；页面可控文本先净化再入日志——换行可
        // 伪造多行 logcat 记录（与 BrowserViewModel 标题净化同口径）。
        android.util.Log.e("AegisHome", sanitizeForLog(message))
    }

    /** AD-235：日志净化（AD-103：收敛 LogSanitize 单源——与标题净化同口径）。 */
    private fun sanitizeForLog(message: String): String = LogSanitize.flatten(message, LOG_MESSAGE_MAX_LENGTH)

    @JavascriptInterface
    fun setEngine(key: String) {
        if (!isTrustedShellPage()) return
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
        if (!isTrustedShellPage()) return ""
        val current = prefs.getString(SearchEngines.KEY_ENGINE, null) ?: SearchEngines.DEFAULT_ENGINE
        return buildEngineJson(current)
    }

    @JavascriptInterface
    fun setWallpaper(name: String) {
        if (!isTrustedShellPage()) return
        if (name in WALLPAPERS) {
            prefs.edit().putString("wallpaper", name).apply()
        }
    }

    @JavascriptInterface
    fun getWallpaper(): String {
        if (!isTrustedShellPage()) return ""
        return prefs.getString("wallpaper", "") ?: ""
    }

    /** 首页搜索/地址栏跳转：归一走 SearchEngines 单源（搜索词/网址同语义）。 */
    @JavascriptInterface
    fun navigate(input: String) {
        if (!isTrustedShellPage()) return
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
        // AD-323：投递经可注入 executor（生产 wv.post；测试同步驱动）
        postToMainThread(wv) {
            val ok = SecureWebViewFactory.navigatorFor(wv)?.navigateExternal(url) == true
            if (!ok) {
                // AD-134（审计 2026-09-23 清单·A6 批）：Toast 文案迁 strings.xml
                // 单源（原硬编码中文——不可本地化、不可静态审查）。
                //
                // AD-192（审计 2026-09-23 清单·A7 批）：applicationContext Toast
                // 保留理由（注释固化）——桥接层按设计不持 Activity 引用
                // （JS 后台线程 + 面向任意远端页面的注入对象，持有宿主即泄漏/
                // 提权面）；Toast 用 app context 构造无 UI 崩溃风险（仅无
                // fly-in 动画差异）；「回调上抛 ViewModel」需从 JS 线程再跨
                // 一次线程边界接线，收益（Snackbar 级提示）不成比例。真机
                // 回归 2026-09-04 起该 Toast 工作正常，维持现状。
                Toast
                    .makeText(context, context.getString(R.string.bridge_open_rejected), Toast.LENGTH_SHORT)
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
        // P1-1 修复（全面审计 2026-09-04）：受信壳页校验合并进 provider 判定（detekt ReturnCount ≤ 2）
        val wv = if (isTrustedShellPage()) webViewProvider() else null
        val navigator = wv?.let(SecureWebViewFactory::navigatorFor)
        if (wv == null || navigator == null) return false
        // WB-106（2026-09-26 审计）：透传 openTrustedAsset 的加载受理结果——
        // 原实现返回 wv != null，导航器缺失/白名单拒绝时仍返回 true，start.js
        // 据此跳过 onFail，「资源未随包 → 按钮置灰」降级在 Android 永不触发
        // （C# 侧正确反映资源可用性）。加载在主线程投递；受理结果经同一
        // 白名单谓词同步判定（与 openTrustedAsset 内部判定单源）。
        wv.post { navigator.openTrustedAsset(SecureNavigator.GEOGEBRA_ASSET_PATH) }
        return navigator.isTrustedAsset(SecureNavigator.GEOGEBRA_ASSET_PATH)
    }

    /**
     * 首页返回按钮（start.html 单源——与 Windows go_back 同名能力）：
     * 经受控导航器逐级回退 WebView 历史栈，无历史时 no-op（不退出应用）。
     */
    @JavascriptInterface
    fun goBack() {
        if (!isTrustedShellPage()) return
        val wv = webViewProvider() ?: return
        wv.post {
            if (wv.canGoBack()) {
                SecureWebViewFactory.navigatorFor(wv)?.navigateHistory(HistoryAction.BACK)
            }
        }
    }
}

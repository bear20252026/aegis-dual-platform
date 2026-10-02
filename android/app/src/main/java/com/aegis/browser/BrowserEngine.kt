package com.aegis.browser

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView

class BrowserEngine(
    private val webView: WebView,
    private val onTitleObserved: (String) -> Unit = {},
) {
    companion object {
        const val HOME_URL = "file:///android_asset/start.html"
        private const val MAX_PROGRESS = 100
        private const val MAX_TITLE_LENGTH = 256

        /**
         * AD-195（审计 2026-09-23 清单·A7 批）：CookieManager 单例持有一次
         * ——configure() 每建一个标签都 `CookieManager.getInstance()` 重复
         * 取单例（每次调用经框架的进程级查找）。lazy 驻留后整个进程只解析
         * 一次；lazy（而非 companion 静态字段直初始化）保证 JVM 单测不触发
         * Android 框架类加载（仅 configure() 真正调用时才解析）。
         */
        private val cookieManager: android.webkit.CookieManager by lazy {
            android.webkit.CookieManager.getInstance()
        }

        /**
         * 只规范化远程 URL；实际外部导航必须由 SecureNavigator 经 Broker 执行。
         *
         * A-3 修复（架构审计 2026-08-31）：原自带的 isAllowed 是全项目最弱的
         * URL 校验（不拒 userinfo/控制字符/超长，host 不小写化）——与决策层
         * OriginPolicy（contracts url-origin-* 向量）语义漂移，同一 URL 展示层
         * 与决策层可得出不同判定。现收敛为 OriginPolicy.tryParseExternal 的
         * 薄封装：补 https 前缀 + host 小写化（对齐 Rust canonicalize_external）。
         *
         * P0-2 修复（搜索审计 2026-09-01）：搜索词 vs 网址判定 + 引擎拼接
         * 下沉到 [SearchEngines.normalizeInput] 单源（与 Windows
         * normalize_url 跨端对齐）——本函数保留薄委托以维持既有调用点兼容。
         */
        fun normalizeExternal(
            input: String,
            engineKey: String = SearchEngines.DEFAULT_ENGINE,
        ): String? = SearchEngines.normalizeInput(input, engineKey)
    }

    @SuppressLint("SetJavaScriptEnabled")
    fun configure() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = false
        webView.settings.allowContentAccess = false
        // AD-292（2026-10-01 审计）：两项 FileURLs 设置 API 26 起 deprecated——
        // 显式置 false 是安全立场声明（默认值随平台演进漂移不可依赖），
        // 抑制编译告警而非删除设置。
        @Suppress("DEPRECATION")
        webView.settings.allowFileAccessFromFileURLs = false
        @Suppress("DEPRECATION")
        webView.settings.allowUniversalAccessFromFileURLs = false
        webView.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        webView.settings.javaScriptCanOpenWindowsAutomatically = false
        webView.settings.setSupportMultipleWindows(false)
        webView.settings.mediaPlaybackRequiresUserGesture = true
        webView.settings.safeBrowsingEnabled = true
        // AD-289（2026-10-01 审计）：显式立场——地理位置与表单自动填充默认
        // 关闭（此前未声明，行为依赖 WebView 默认值漂移；WebSettings 无
        // isGeolocationEnabled 公开 getter，JVM 侧无法断言——断言面见
        // BrowserEngineHardeningTest 的 saveFormData 与真机冒烟）。
        // setSaveFormData 在 API 26+ 标记 deprecated（平台侧已不保存表单数据，
        // 显式置 false 是「fail-closed 立场声明」而非功能变更）。
        webView.settings.setGeolocationEnabled(false)
        @Suppress("DEPRECATION")
        webView.settings.setSaveFormData(false)
        // 移动端渲染优化——页面适配手机屏幕，不再"粗糙"
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = true
        webView.settings.setSupportZoom(true)
        webView.settings.builtInZoomControls = true
        webView.settings.displayZoomControls = false
        // AD-325（2026-10-02 审计）：删除 textZoom=100 钉死——该行覆盖系统
        // 字体缩放（fontScale），大字号用户的 web 正文不随系统设置放大
        //（系统级无障碍回退）。回归平台默认（textZoom 默认随 fontScale
        // 派生）；TEXT_ZOOM_DEFAULT 常量随之清理（无其他引用）。
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        // WebViewClient 由 SecureWebViewFactory 统一注入 AegisWebViewClient（经 Broker 决策），
        // BrowserEngine 不得覆盖——单路径收敛（专家审计）。
        // onPageStarted/onPageFinished 的日志由 AegisWebViewClient 回调替代。
        // 下载由 Broker→Executor 单路径处理（INV-02：Executor 是唯一副作用点）——
        // BrowserEngine 不再直接处理下载（单路径收敛——专家审计）。
        // A-02 整改（国防级审查）：WebChromeClient——权限/文件选择默认拒绝
        // （Android 官方：不可信内容不授予权限；onShowFileChooser 无来源校验）
        webView.webChromeClient =
            object : WebChromeClient() {
                override fun onPermissionRequest(request: PermissionRequest) {
                    request.deny()
                }

                override fun onShowFileChooser(
                    webView: WebView,
                    filePathCallback: ValueCallback<Array<Uri>>,
                    fileChooserParams: WebChromeClient.FileChooserParams,
                ): Boolean = false

                // R-12 整改（体验/功能审查）：进度/标题回调——状态同步事件
                // （onProgressChanged/onReceivedTitle——地址栏/标签标题同步）
                override fun onProgressChanged(
                    view: WebView,
                    newProgress: Int,
                ) {
                    // AD-232（2026-09-26 审计）：进度日志降级——原实现每次进度
                    // 变化都 Log.i（每页 5-10 条永久 info 噪声）；仅完成留痕，
                    // 中间进度仅 debug 构建可见。
                    val progress = newProgress.coerceIn(0, MAX_PROGRESS)
                    if (BuildConfig.DEBUG || progress >= MAX_PROGRESS) {
                        android.util.Log.i("Aegis", "R12 progress: $progress")
                    }
                }

                override fun onReceivedTitle(
                    view: WebView,
                    title: String?,
                ) {
                    // P0 修复（全库审计 2026-09-02）：标题此前仅打日志——Tab.title
                    // 全工程无回填点，标签栏永远显示「新标签页」。经工厂回调单路径
                    // 上抛 ViewModel（对齐 onPageUrlObserved 同一接线模式）。
                    // AD-171（审计 2026-09-23 清单·A7 批）：本处原还有一条
                    // `Log.i("R12 title: …")`——远端可控标题逐页打永久 info
                    // （死回调噪声），且 WebViewEventAssembly.onTitleObserved
                    // 已有净化截断的 titleHit 日志（DEBUG 门控，AD-172）——
                    // 本行纯属重复留痕，随批移除。
                    // AD-268（2026-10-01 审计）：take 改代理对安全截断——
                    // String.take 按 UTF-16 char 劈切，切点落在增补字符
                    // （emoji 等）中间产生孤立代理对（渲染 � 且 length 失真）
                    // ——AD-308 起与 LogSanitize 共用 takeAtCharBoundary 顶层函数。
                    val safeTitle = takeAtCharBoundary(title.orEmpty(), MAX_TITLE_LENGTH)
                    onTitleObserved(safeTitle)
                }
            }
        // A-03 整改（国防级审查）：默认限制第三方 Cookie（WebView 默认
        // 接受——审查要求显式限制，防跨站追踪）。
        // AD-195：单例经 companion 持有（进程内一次解析）。
        cookieManager.setAcceptThirdPartyCookies(webView, false)
    }
}

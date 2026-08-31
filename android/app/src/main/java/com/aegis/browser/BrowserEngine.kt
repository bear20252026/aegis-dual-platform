package com.aegis.browser

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.PermissionRequest
import android.webkit.RenderProcessGoneDetail
import android.webkit.SafeBrowsingResponse
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.aegis.broker.OriginPolicy

class BrowserEngine(
    private val webView: WebView,
) {
    companion object {
        const val HOME_URL = "file:///android_asset/start.html"
        private const val MAX_PROGRESS = 100
        private const val MAX_TITLE_LENGTH = 256
        private const val TEXT_ZOOM_DEFAULT = 100

        /**
         * 只规范化远程 URL；实际外部导航必须由 SecureNavigator 经 Broker 执行。
         *
         * A-3 修复（架构审计 2026-08-31）：原自带的 isAllowed 是全项目最弱的
         * URL 校验（不拒 userinfo/控制字符/超长，host 不小写化）——与决策层
         * OriginPolicy（contracts url-origin-* 向量）语义漂移，同一 URL 展示层
         * 与决策层可得出不同判定。现收敛为 OriginPolicy.tryParseExternal 的
         * 薄封装：补 https 前缀 + host 小写化（对齐 Rust canonicalize_external）。
         */
        fun normalizeExternal(input: String): String? =
            input
                .trim()
                .takeIf { it.isNotEmpty() }
                ?.let { candidate -> if (candidate.contains("://")) candidate else "https://$candidate" }
                ?.let(OriginPolicy::tryParseExternal)
                ?.let(::canonicalize)

        private fun canonicalize(uri: java.net.URI): String? {
            val host = uri.host?.lowercase() ?: return null
            val port =
                uri.port
                    .takeIf { it != -1 }
                    ?.let { ":$it" }
                    .orEmpty()
            return buildString {
                append(uri.scheme).append("://").append(host).append(port)
                uri.rawPath?.let { append(it) }
                uri.rawQuery?.let { append('?').append(it) }
                uri.rawFragment?.let { append('#').append(it) }
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    fun configure() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = false
        webView.settings.allowContentAccess = false
        webView.settings.allowFileAccessFromFileURLs = false
        webView.settings.allowUniversalAccessFromFileURLs = false
        webView.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        webView.settings.javaScriptCanOpenWindowsAutomatically = false
        webView.settings.setSupportMultipleWindows(false)
        webView.settings.mediaPlaybackRequiresUserGesture = true
        webView.settings.safeBrowsingEnabled = true
        // 移动端渲染优化——页面适配手机屏幕，不再"粗糙"
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = true
        webView.settings.setSupportZoom(true)
        webView.settings.builtInZoomControls = true
        webView.settings.displayZoomControls = false
        webView.settings.textZoom = TEXT_ZOOM_DEFAULT
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
                    android.util.Log.i("Aegis", "R12 progress: ${newProgress.coerceIn(0, MAX_PROGRESS)}")
                }

                override fun onReceivedTitle(
                    view: WebView,
                    title: String?,
                ) {
                    android.util.Log.i("Aegis", "R12 title: ${title?.take(MAX_TITLE_LENGTH).orEmpty()}")
                }
            }
        // A-03 整改（国防级审查）：默认限制第三方 Cookie（WebView 默认
        // 接受——审查要求显式限制，防跨站追踪）
        android.webkit.CookieManager
            .getInstance()
            .setAcceptThirdPartyCookies(webView, false)
    }

    /** A-03 整改（国防级审查）：无痕/会话结束清理序列（Cookie/缓存/历史）。 */
    fun clearPrivateData() {
        android.webkit.CookieManager
            .getInstance()
            .removeAllCookies(null)
        webView.clearCache(true)
        webView.clearHistory()
    }
}

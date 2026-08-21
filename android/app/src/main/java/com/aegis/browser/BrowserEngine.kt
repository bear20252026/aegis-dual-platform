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
import java.net.URI

class BrowserEngine(
    private val webView: WebView,
) {
    companion object {
        private val allowedSchemes = setOf("http", "https")
        private const val MAX_PROGRESS = 100
        private const val MAX_TITLE_LENGTH = 256
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

    fun load(url: String) {
        val normalized = normalize(url) ?: return
        webView.loadUrl(normalized)
    }

    fun canNavigate(url: String): Boolean = normalize(url) != null

    private fun normalize(input: String): String? {
        val candidate = input.trim()
        if (candidate.isEmpty()) return null
        val withScheme = if (candidate.contains("://")) candidate else "https://$candidate"
        return if (isAllowed(withScheme)) withScheme else null
    }

    private fun isAllowed(url: String): Boolean =
        runCatching {
            val uri = URI(url)
            uri.scheme?.lowercase() in allowedSchemes && !uri.host.isNullOrBlank()
        }.getOrDefault(false)
}

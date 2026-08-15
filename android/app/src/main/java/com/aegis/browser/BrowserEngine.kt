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
        webView.webViewClient =
            object : WebViewClient() {
                override fun shouldOverrideUrlLoading(
                    view: WebView,
                    request: WebResourceRequest,
                ): Boolean = !isAllowed(request.url.toString())

                // A-02 整改（国防级审查）：渲染器崩溃——保持系统默认（不静默吞掉）
                override fun onRenderProcessGone(
                    view: WebView,
                    detail: RenderProcessGoneDetail,
                ): Boolean = super.onRenderProcessGone(view, detail)

                // A-08 整改（国防级审查）：Safe Browsing 命中默认阻断（不
                // 继续到恶意页——Android 官方保持用户安全）+ 审计记录
                override fun onSafeBrowsingHit(
                    view: WebView,
                    request: WebResourceRequest,
                    threatType: Int,
                    callback: SafeBrowsingResponse,
                ) {
                    callback.backToSafety(true)
                    android.util.Log.w("Aegis", "SafeBrowsing 命中阻断: ${request.url} threatType=$threatType")
                }

                // R-12 整改（体验/功能审查）：页面加载事件——地址/标题/进度
                // 同步（单向状态流事件——状态消费/UI 更新为发布期 ViewModel）
                override fun onPageStarted(
                    view: WebView,
                    url: String?,
                    favicon: android.graphics.Bitmap?,
                ) {
                    android.util.Log.i("Aegis", "R12 pageStarted: $url")
                }

                override fun onPageFinished(view: WebView, url: String?) {
                    android.util.Log.i("Aegis", "R12 pageFinished: $url")
                }
            }
        // A-02 整改（国防级审查）：下载接入 DownloadPolicy——危险扩展名
        // （exe/ps1/lnk 等）默认拒绝（发布期可接入原生确认 UI——A-07 最小化）
        webView.setDownloadListener { url, _, _, _, _ ->
            if (DownloadPolicy.requiresExplicitConfirmation(url)) {
                android.util.Log.w("Aegis", "拒绝危险下载: $url")
            } else {
                android.util.Log.i("Aegis", "受控下载: $url")
            }
        }
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
                override fun onProgressChanged(view: WebView, newProgress: Int) {
                    android.util.Log.i("Aegis", "R12 progress: ${newProgress.coerceIn(0, 100)}")
                }

                override fun onReceivedTitle(view: WebView, title: String?) {
                    android.util.Log.i("Aegis", "R12 title: ${title?.take(256).orEmpty()}")
                }
            }
        // A-03 整改（国防级审查）：默认限制第三方 Cookie（WebView 默认
        // 接受——审查要求显式限制，防跨站追踪）
        android.webkit.CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false)
    }

    /** A-03 整改（国防级审查）：无痕/会话结束清理序列（Cookie/缓存/历史）。 */
    fun clearPrivateData() {
        android.webkit.CookieManager.getInstance().removeAllCookies(null)
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

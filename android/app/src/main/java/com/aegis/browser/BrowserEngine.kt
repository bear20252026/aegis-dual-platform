package com.aegis.browser

import android.annotation.SuppressLint
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
            }
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

package com.aegis.browser

import android.content.Context
import android.webkit.WebView

/**
 * 安全 WebView 工厂（单文件单职责：统一创建带完整安全边界的 WebView）。
 *
 * 背景（S4 修复 M1）：原 MainActivity 中 `BrowserEngine(view).configure()`
 * 与 `BrowserEngine(view).load(address)` 各 new 一个 BrowserEngine 实例，
 * 且每个新标签都要手工重复安全配置。本工厂把"创建 + 安全配置"收敛为
 * 唯一入口 —— 所有标签（含未来新增）都必须经此创建，保证：
 *   1. 安全设置零遗漏（http/https 白名单、禁 file/混合内容/调试等）；
 *   2. 一处配置、处处生效，后续加安全策略只改这里。
 */
object SecureWebViewFactory {
    /** 创建并完成安全配置的 WebView。 */
    fun create(context: Context): WebView {
        val webView = WebView(context)
        BrowserEngine(webView).configure()
        return webView
    }
}

package com.aegis.browser

import android.net.Uri

/**
 * 整页翻译入口（CHANGELOG Planned：Android 整页翻译入口）。
 *
 * 职责：把当前页 URL 包装为微软 Edge 同款整页翻译服务地址
 * （translatetheweb.com——国内可达）；导航本身仍经
 * SecureNavigator.navigateExternal（http/https 白名单 + Broker 授权）。
 *
 * 隐私边界：整页翻译必然把目标 URL 发送给翻译服务——本类只提供
 * 入口构建，用户在 UI 显式点击后才发生导航（与 Aegis「默认不外发、
 * 用户显式授权」的隐私原则一致）。
 */
object TranslateEntry {
    /** 翻译目标语言（简体中文）。 */
    private const val TARGET_LANG = "zh-Hans"

    private const val SERVICE = "https://www.translatetheweb.com/"

    /**
     * 构建整页翻译 URL；pageUrl 非 http/https 返回 null
     * （本地壳页/about: 页无翻译意义，也不应外发）。
     */
    fun buildUrl(pageUrl: String?): String? {
        val url = pageUrl?.trim().orEmpty()
        if (!url.startsWith("http://") && !url.startsWith("https://")) return null
        val encoded = Uri.encode(url)
        return "$SERVICE?from=auto&to=$TARGET_LANG&a=$encoded"
    }
}

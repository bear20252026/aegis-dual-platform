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
        // AD-231（2026-09-26 审计）：scheme 判定大小写不敏感——决策层
        // （OriginPolicy/schemePrefixOf）均忽略大小写，HTTP:// 页面翻译
        // 此前被拒（口径不一致）。
        if (!url.startsWith("http://", ignoreCase = true) && !url.startsWith("https://", ignoreCase = true)) {
            return null
        }
        // AD-280（2026-10-01 审计）：fragment 先剥再编码——fragment 不参与
        // 服务端取页（Authorization Code/session token 常以 #access_token=
        // 形态留在 URL 尾部，fragment 是其唯一载体），外发翻译服务即凭据
        // 泄漏面。翻译服务取页只消费 scheme://authority/path?query。
        val encoded = Uri.encode(url.substringBefore('#'))
        return "$SERVICE?from=auto&to=$TARGET_LANG&a=$encoded"
    }
}

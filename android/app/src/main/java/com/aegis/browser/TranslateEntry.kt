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
     * AD-313（2026-10-02 审计）：外发前剥离的敏感查询参数名（小写比较）——
     * OAuth Authorization Code 实际经 query 流转（?code=…&state=…），并非只
     * 在 fragment；会话/CSRF token 同为 query 常客。翻译服务取页不需要它们，
     * 原样外发即凭据泄漏面。
     */
    private val SENSITIVE_QUERY_PARAMS = setOf("code", "state", "token")

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
        // 服务端取页（session token 常以 #access_token= 形态留在 URL 尾部），
        // 外发翻译服务即凭据泄漏面。
        // AD-313（2026-10-02 审计）注释修正：凭据并非「fragment 是其唯一
        // 载体」——OAuth Code/State 与各色 token 实际主要经 query 流转；
        // 整 URL（含 query）原样编码外发才是泄漏面主体。配套：query 中
        // 已知敏感参数（[SENSITIVE_QUERY_PARAMS]）剥离后再外发。
        val sanitized = stripSensitiveQueryParams(url.substringBefore('#'))
        val encoded = Uri.encode(sanitized)
        return "$SERVICE?from=auto&to=$TARGET_LANG&a=$encoded"
    }

    /**
     * AD-313：剥离 query 中的敏感参数（code/state/token——名称大小写不敏感）。
     * 纯字符串实现（JVM 可测）：参数名取 '=' 前段；无 query 或无命中原样
     * 返回；全量剥空时移除 '?'（翻译服务取页不依赖空 query）。
     */
    internal fun stripSensitiveQueryParams(urlWithoutFragment: String): String {
        val queryStart = urlWithoutFragment.indexOf('?')
        if (queryStart < 0) return urlWithoutFragment
        val base = urlWithoutFragment.substring(0, queryStart)
        val entries = urlWithoutFragment.substring(queryStart + 1).split('&')
        val kept =
            entries.filter { entry ->
                entry.substringBefore('=').lowercase() !in SENSITIVE_QUERY_PARAMS
            }
        // 无命中：原样返回（保留用户 URL 字节形态）
        if (kept.size == entries.size) return urlWithoutFragment
        return if (kept.isEmpty()) base else "$base?${kept.joinToString("&")}"
    }
}

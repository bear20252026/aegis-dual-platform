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
    private val SENSITIVE_QUERY_PARAMS =
        setOf("code", "state", "token", "key", "auth", "sid", "sig", "nonce")

    /**
     * R9-AD-2（第九轮 2026-10-10）：AD-313 的精确名单漏掉真实世界更常见的**词干**形态——
     * `access_token`/`refresh_token`/`id_token`/`csrf_token` 都不等于 `token`，
     * `api_key`/`apikey` 不等于 `key`，`sessionid`/`jsessionid` 不在名单里；这些形态
     * 原样编码外发翻译服务就是凭据泄漏面。
     *
     * 规则：参数名小写并去掉 `-`/`_` 后，命中下列词干（contains）即剥离。
     * **刻意不把 `key` 放进词干**——`keywords`/`keyboard` 这类良性参数会被误剥，
     * 而翻译服务取页可能依赖它们（`key` 本身仍在精确名单里）。同理不放 `id`/`code`。
     */
    private val SENSITIVE_PARAM_STEMS =
        listOf(
            "token",
            "secret",
            "password",
            "passwd",
            "credential",
            "apikey",
            "session",
            "authorization",
            "signature",
            "csrf",
            "xsrf",
        )

    /**
     * 名字是否为凭据形态（R9-AD-2）。纯字符串、无 Android 依赖 ⇒ JVM 可直测。
     */
    internal fun isSensitiveParam(rawName: String): Boolean {
        val normalized = rawName.lowercase().replace("-", "").replace("_", "")
        return normalized in SENSITIVE_QUERY_PARAMS || SENSITIVE_PARAM_STEMS.any { normalized.contains(it) }
    }

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
        // 已知凭据形态参数（[isSensitiveParam]）剥离后再外发。
        val sanitized = stripSensitiveQueryParams(url.substringBefore('#'))
        val encoded = Uri.encode(sanitized)
        return "$SERVICE?from=auto&to=$TARGET_LANG&a=$encoded"
    }

    /**
     * AD-313 + R9-AD-2：剥离 query 中的凭据形态参数——精确名单（code/state/token/
     * key/auth/sid/sig/nonce）加词干匹配（token/secret/password/passwd/credential/apikey/
     * session/authorization/signature/csrf/xsrf），名称大小写与 `-`/`_` 分隔不敏感。
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
                !isSensitiveParam(entry.substringBefore('='))
            }
        // detekt-修复（2026-10-02 审计云端实证）：ReturnCount(3>2)——命中分型收敛
        // 为 when 表达式（无命中原样返回/全量剥空移除 '?'/部分剥离重组）。
        return when {
            kept.size == entries.size -> urlWithoutFragment
            kept.isEmpty() -> base
            else -> "$base?${kept.joinToString("&")}"
        }
    }
}

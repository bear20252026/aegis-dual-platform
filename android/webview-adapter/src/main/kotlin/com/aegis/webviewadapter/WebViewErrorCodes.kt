package com.aegis.webviewadapter

import com.aegis.broker.DenyReason

/**
 * AD-102（审计 2026-09-23 清单·A6 批）：错误码契约单文件——原 ERROR_* 常量
 * 与 denialLogLine 内嵌在 AegisWebViewClient companion，客户端文件超改造
 * 红线且错误契约与回调装配混居。抽出后：
 * - app 层（BrowserViewModel/PageErrorTexts）按本对象映射文案（AD-035 分层
 *   的常量面收敛到此单源，杜绝字面量双源漂移——AD-136 的 onPageError 调用点
 *   字面量改引常量即本项配套）；
 * - 跨模块（app ↔ webview-adapter）契约必须 public——internal 是模块级可见性。
 */
object WebViewErrorCodes {
    /** P2-1 修复：HTTP 错误状态码阈值（>= 该值视为服务器端错误）。 */
    const val HTTP_ERROR_MIN = 400

    /** SSL 证书错误（detail = SslError.primaryError 整数值）。 */
    const val ERROR_SSL_CERTIFICATE = "ssl_certificate_error"

    /** 主框架加载失败（detail = "errorCode:description"）。 */
    const val ERROR_MAIN_FRAME = "main_frame_error"

    /** 主框架 HTTP >= 400（detail = 状态码字符串）。 */
    const val ERROR_HTTP = "http_error"

    /**
     * 审计第六轮（2026-10-03）：授权兑换失败（consumeNavigation 返回 false——
     * 会话过期/代际不符/nonce 重放/Kotlin 侧 expiresAt 已到）。broker 只回
     * 布尔、无原生 deny code 可透传，此前表现为「点了没反应」的静默死链；
     * 现由客户端补此码经 onNavigationDenied 顶层上抛（app 层回落
     * nav_rejected_code 文案带出 code——拒绝必须用户可见）。
     */
    const val ERROR_NAVIGATION_NOT_CONSUMED = "navigation_not_consumed"

    /**
     * AD-211（2026-09-26 审计）：拒绝日志整行组装单源——detail 与 url
     * 一并脱敏。原实现只对 url 参数走 LogRedact，但 AndroidBroker/Rust
     * 核心的 deny detail 内嵌完整明文 URL（`拒绝 URL: $rawUrl` 直接拼
     * 原文），query 中的 token/搜索词经 detail 绕过 AD-004 脱敏入
     * logcat。internal 供 JVM 单测断言「日志行不含明文 query」。
     */
    internal fun denialLogLine(
        reason: DenyReason,
        url: String,
    ): String =
        "导航被拒: code=${reason.code} detail=${LogRedact.redact(reason.detail)} " +
            "url=${LogRedact.redact(url)}"
}

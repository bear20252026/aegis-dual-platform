package com.aegis.broker

import java.net.URI

/**
 * URI → 规范 origin / canonicalParameters（自 `AndroidBroker` 外移，R9-B95）。
 *
 * 为什么外移：那个文件停在 447 行的**基线额度上**（SP-255 是 ratchet：基线内只许减不许增），
 * 而本批要给它加一个「把名单灌进核心」的公开入口。归一化是纯函数（不碰会话表、不碰 nonce
 * 账本、不碰 JNI），拆出来让两侧职责各自单一：桥接面管生命周期与授权，这里只管字节口径。
 * `AndroidBroker` 保留同名委托，故既有引用面（含 `AndroidBrokerTest` 的 AD-249 那组直测）
 * 逐字不变——外移不能以改测试为代价，否则「重构」与「改行为」混在一次提交里没法评审。
 */
internal object UriCanonical {
    /**
     * AD-180（审计 2026-09-23 清单·A7 批）：scheme → 默认端口查表——
     * 原 `if (https) 443 else 80` 把一切非 https scheme 都折叠成 80
     * （脆弱：新增 scheme 时默认端口静默错误）。改为显式查表，未知
     * scheme 无默认端口（始终按显式端口展示处理——端口折叠只对
     * 表内 scheme 生效）。
     */
    private val DEFAULT_PORTS = mapOf("http" to 80, "https" to 443)

    /**
     * AD-249（2026-09-26 审计）：internal 化供 JVM 单测直接断言——IPv6 host、
     * 非默认端口拼接与默认端口折叠此前仅经 evaluateNavigation 间接覆盖。
     */
    fun origin(uri: URI): String {
        // T2 配套（全面审计批次2 2026-09-04）：about:blank 为 opaque URI
        // （host=null）——直接归一会 NPE；固定返回原字面量。
        if (uri.scheme.equals("about", ignoreCase = true)) return "about:blank"
        val scheme = uri.scheme.lowercase()
        val port = uri.port
        // AD-180：默认端口查表（未知 scheme 无默认端口 → 端口一律显式展示）
        val defaultPort = DEFAULT_PORTS[scheme]
        val authority =
            if (port == -1 || defaultPort == port) {
                uri.host.lowercase()
            } else {
                "${uri.host.lowercase()}:$port"
            }
        return "$scheme://$authority"
    }

    fun pathAndQuery(uri: URI): String {
        val path = uri.rawPath?.ifEmpty { "/" } ?: "/"
        return uri.rawQuery?.let { "$path?$it" } ?: path
    }
}

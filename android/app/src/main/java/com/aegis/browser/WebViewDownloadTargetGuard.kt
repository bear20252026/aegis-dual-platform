package com.aegis.browser

import android.content.Context
import android.widget.Toast
import com.aegis.broker.ReservedAddressBoundary
import com.aegis.webviewadapter.LogRedact

/**
 * 下载目标形态闸门（R8-AD-03，第八轮 2026-10-08；自 [WebViewDownloadHandler] 拆出——
 * 该文件的行数基线只许减不许增，拆出同时是收窄）。
 *
 * 只拦两类**根本不该发起的下载**，其余一律放行：
 * • 非 http/https scheme——系统 `DownloadManager` 不支持 blob/data 等形态；
 * • **保留地址**：链路本地（云厂商实例元数据 `169.254.169.254` 在其内）、`0/8`、
 *   组播/广播/保留、TEST-NET-1/2/3、`198.18/15`，IPv6 的 `::`/`fe80::/10`/`ff00::/8`，
 *   以及与 OS 解释分歧的数字形态。段表单源在 `:broker` 的 [ReservedAddressBoundary]，
 *   与 Windows 孪生同口径、同拒绝码。
 *
 * 为什么下载层要单独判（不是重复导航层）：下载交系统 `DownloadProvider` 执行，那是
 * **另一个进程** ⇒ 本 app 的 `network_security_config.xml`（禁明文）管不到它。于是
 * 「明文 + 链路本地」这类在导航层被拒、在子资源层被 NSC 挡的形态，在下载层此前
 * 完整绕过，并把 user-data 落盘到公共下载目录。
 *
 * 上界是第七轮 B8 裁决「本机与内网必须能打开」：回环 / RFC1918 / CGNAT(100.64/10) /
 * ULA(fc00::/7) 与 `localhost`·`.local`·`.internal` 主机名照旧可下载——不得把这条
 * 差异当 SSRF 缺陷反向收紧。已知代价照抄 Windows 侧的账：阿里云元数据
 * `100.100.100.200` 落在按裁决放行的 CGNAT 段内，记入残余而不假称已封。
 */
internal object WebViewDownloadTargetGuard {
    /**
     * 纯判定（零 Android 类型 ⇒ JVM 可测）：命中拦截 ⇒ 返回「脱敏留痕文本 to 文案资源
     * id」，放行 ⇒ null。scheme 由调用方给出（`android.net.Uri` 只出现在 UI 侧，
     * 不进这条判据——本仓不欢迎第二个 URL 解析器）。
     */
    fun rejectionOf(
        url: String,
        scheme: String?,
    ): Pair<String, Int>? =
        when {
            scheme != "http" && scheme != "https" ->
                "拦截非 http(s) 下载: $scheme" to R.string.download_blocked_type
            ReservedAddressBoundary.denies(url) ->
                "拦截指向保留地址的下载: ${LogRedact.redact(url)} code=${ReservedAddressBoundary.DENY_CODE}" to
                    R.string.download_blocked_reserved
            else -> null
        }

    /** 接线：命中即脱敏留痕 + Toast 明示用户，绝不静默放行（true = 已拦，不得入队）。 */
    fun interceptIfRejected(
        context: Context,
        url: String,
        scheme: String?,
    ): Boolean {
        val rejection = rejectionOf(url, scheme) ?: return false
        android.util.Log.w("AegisDownload", rejection.first)
        Toast.makeText(context, context.getString(rejection.second), Toast.LENGTH_LONG).show()
        return true
    }
}

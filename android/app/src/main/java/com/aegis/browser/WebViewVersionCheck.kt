package com.aegis.browser

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.pm.PackageInfoCompat
import androidx.webkit.WebViewCompat

/**
 * Android System WebView 版本检查（单文件单职责：CVE-2026-12438/11295 防御）。
 *
 * 背景（final-development-checklist.md A1）：Android System WebView 是 2026 年
 * 被积极攻击的目标（CVE-2026-12438 沙箱逃逸、CVE-2026-11295 权限提升）——
 * 建立"版本检查 + 提示更新"机制，提示用户将 System WebView 更新到最新安全版本。
 *
 * 设计：纯逻辑单文件（版本获取/阈值比较/提示回调），UI 提示由调用方
 * （MainActivity）呈现——与项目"单文件单职责"惯例一致。
 * AD-234（2026-09-26 审计）：修正口径失实——本检查只提示不阻断（版本过旧
 * 仍可浏览，仅弹更新建议对话框）；旧注释宣称「版本低于安全阈值时拒绝外部
 * 浏览」从未落地，行为与声明对齐后按「提示」表述。
 */
object WebViewVersionCheck {
    /** Android System WebView 包名（Google 发行版——更新跳转目标）。 */
    private const val WEBVIEW_PKG = "com.google.android.webview"

    /**
     * 最低安全版本阈值（versionCode）。
     * 注：需按 Google 安全公告动态更新（CVE-2026-12438/11295 对应版本
     * 以官方公告为准）；此处为可配置常量，随安全公告维护。
     */
    private const val MIN_SAFE_VERSION_CODE = 132_000_000

    /** 版本信息（versionName, versionCode）；未安装返回 null（静默）。 */
    data class WebViewVersion(
        val name: String,
        val code: Long,
    )

    /**
     * 获取当前 WebView 提供方版本；未安装/异常返回 null（不阻塞浏览）。
     *
     * AD-218（2026-09-26 审计）：改经 WebViewCompat.getCurrentWebViewPackage——
     * 原实现仅探测 com.google.android.webview：AOSP com.android.webview、
     * Chrome 代打 provider、厂商包上 getPackageInfo 必抛 NameNotFoundException
     * → null 静默返回，过旧 WebView 提示完全失效。当前 provider 由框架解析
     * （含多 provider 与选择逻辑）；versionCode 取 longVersionCode
     * （经 PackageInfoCompat——minSdk 26 无字段直读）。
     */
    fun getWebViewVersion(context: Context): WebViewVersion? =
        try {
            WebViewCompat.getCurrentWebViewPackage(context)?.let { pkg ->
                WebViewVersion(
                    name = pkg.versionName ?: "unknown",
                    code = PackageInfoCompat.getLongVersionCode(pkg),
                )
            }
        } catch (_: Exception) {
            null
        }

    /** 版本是否过旧（低于最低安全阈值）。 */
    fun isOutdated(versionCode: Long): Boolean = versionCode < MIN_SAFE_VERSION_CODE

    /** 检查并触发提示（版本过旧时回调提示文案；由调用方呈现 UI）。 */
    fun checkAndPrompt(
        context: Context,
        onOutdated: (String) -> Unit,
    ) {
        val v = getWebViewVersion(context) ?: return
        if (isOutdated(v.code)) {
            onOutdated(
                "Android System WebView 版本过旧（${v.name}），建议更新以修复已知安全漏洞" +
                    "（CVE-2026-12438/11295）。",
            )
        }
    }

    /** 跳转 WebView 更新入口（Play Store 详情页；失败静默）。 */
    fun openUpdate(context: Context) {
        try {
            context.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$WEBVIEW_PKG")),
            )
        } catch (_: Exception) {
            try {
                context.startActivity(
                    Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$WEBVIEW_PKG")),
                )
            } catch (_: Exception) {
                // 静默：无法打开更新入口不影响浏览
            }
        }
    }
}

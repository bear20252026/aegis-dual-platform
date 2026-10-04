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

    // 最低安全版本阈值——**版本名口径**（major / build 两段）。
    //
    // R7-AD-01（第七轮 2026-10-04）：此前阈值写成 `132_000_000L` 直接与
    // `getLongVersionCode` 比较。Chromium 的 longVersionCode 是十位量级——本仓
    // WebViewVersionCheckProviderTest 自己就用 `141_000_7390L` 表示
    // `141.0.7390.0`——于是 1.32×10⁸ 反推回版本只约等于 m40 时代，任何能跑
    // minSdk 26 的设备恒判「版本安全」，MainActivity 声明的 CVE-2026-12438/11295
    // 提示在全部出货设备上静默为零。改取版本名的数字段比较，不再依赖各发行版
    // 并不一致的后缀编码；随安全公告维护时只改本对常量。
    internal const val MIN_SAFE_MAJOR = 132
    internal const val MIN_SAFE_BUILD = 0

    // 版本名分隔（非数字段）——厂商后缀（"-bugfix"）与四段式共用一套解析
    private val VERSION_SEGMENT_SEPARATOR = Regex("[^0-9]+")

    // build 段在数字序列中的下标（major, minor, build[, patch]）
    private const val BUILD_SEGMENT_INDEX = 2

    // 判定所需的最少数字段数——单段（"141"）不足以区分同主版本内的构建
    private const val MIN_VERSION_SEGMENTS = 2

    // 两段形态（"132.0"）下的 build 取值
    private const val ZERO_BUILD = 0

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

    /**
     * 解析版本名的数字前缀（major, build）——`141.0.7390.0` → (141, 7390)。
     * 厂商后缀（`141.0.7390.163-bugfix`）、缺段（`141`）、非数字段都按不可判定
     * 返回 null（调用方 fail-closed 到"提示更新"一侧，绝不静默判安全）。
     */
    internal fun parseVersion(name: String): Pair<Int, Int>? {
        val numbers =
            name
                .split(VERSION_SEGMENT_SEPARATOR)
                .mapNotNull { it.toIntOrNull() }
        val major = numbers.firstOrNull()
        val build =
            when {
                // 一段（"141"）或空——build 段无从判定，不猜
                numbers.size < MIN_VERSION_SEGMENTS -> null

                // 两段（"132.0"）——Chromium 版本恒为四段，此处按公告口径视作 build 0
                numbers.size == MIN_VERSION_SEGMENTS -> ZERO_BUILD

                else -> numbers.getOrNull(BUILD_SEGMENT_INDEX)
            }
        return if (major != null && build != null) major to build else null
    }

    /** 版本是否过旧（低于最低安全阈值）。取版本名口径，见 [MIN_SAFE_MAJOR]。 */
    fun isOutdated(version: WebViewVersion): Boolean {
        val parsed = parseVersion(version.name) ?: return true
        val (major, build) = parsed
        return major < MIN_SAFE_MAJOR ||
            (major == MIN_SAFE_MAJOR && build < MIN_SAFE_BUILD)
    }

    /** 检查并触发提示（版本过旧时回调提示文案；由调用方呈现 UI）。
     *  AD-135（审计 2026-09-23 清单·A6 批）：提示文案迁 strings.xml 单源
     *  （原硬编码中文——不可本地化、不可静态审查）。 */
    fun checkAndPrompt(
        context: Context,
        onOutdated: (String) -> Unit,
    ) {
        val v = getWebViewVersion(context) ?: return
        if (isOutdated(v)) {
            onOutdated(context.getString(R.string.webview_outdated, v.name))
        }
    }

    /**
     * AD-205（审计 2026-09-23 清单·A7 批）：更新入口双跳转链路抽纯函数单源
     * ——候选 Intent 列表显式化：①Play Store 详情页（market://，安装了
     * 商店的设备首选）；②Web 兜底（https://play.google.com/…，无商店/
     * 商店解析失败时经浏览器打开）。链路次序即契约，openUpdate 按序尝试。
     * （Robolectric 下断言两个候选的 action/uri 与次序——原双跳转零测试。）
     */
    internal fun updateIntents(): List<Intent> =
        listOf(
            Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$WEBVIEW_PKG")),
            Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$WEBVIEW_PKG")),
        )

    /**
     * 跳转 WebView 更新入口（Play Store 详情页 → Web 兜底）。
     *
     * AD-204（审计 2026-09-23 清单·A7 批）：返回受理结果供失败降级——原实现
     * 两级 try/catch 全部静默吞掉（无商店且无浏览器的设备上点「去更新」
     * 毫无反馈，用户无从得知降级链路已走到尽头）。现逐候选尝试并返回
     * 是否成功发起跳转；调用方（MainActivity）失败时回填提示文案。
     *
     * [startActivity] 参数为跳转动作的注入接缝（默认 Context.startActivity）
     * ——失败/成功路径均可离线单测（WebViewVersionCheckTest），无需真机
     * 构造「双候选皆不可解析」的环境。
     */
    fun openUpdate(
        context: Context,
        startActivity: (Intent) -> Unit = context::startActivity,
    ): Boolean {
        // 可预见的跳转失败集：无候选解析（ActivityNotFoundException——无商店/
        // 无浏览器）与系统拒绝（SecurityException）。不吞一切异常：其它异常
        // 类型属非预期状态，应当面暴露而非折叠成「无法更新」。
        var lastError: Exception? = null
        for (intent in updateIntents()) {
            try {
                startActivity(intent)
                return true
            } catch (e: android.content.ActivityNotFoundException) {
                lastError = e
            } catch (e: SecurityException) {
                lastError = e
            }
        }
        // 全部候选失败：留痕后交由调用方降级（不再静默——AD-204）
        android.util.Log.w("Aegis", "WebView 更新入口全部跳转失败: ${lastError?.javaClass?.simpleName}")
        return false
    }
}

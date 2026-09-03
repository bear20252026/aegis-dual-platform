package com.aegis.browser

import android.net.Uri
import com.aegis.broker.OriginPolicy

/**
 * 搜索引擎表 + 输入归一单源（搜索功能审计 2026-09-01）。
 *
 * P0-2 修复：Android 原生地址栏此前没有"搜索词 vs 网址"判断——输入
 * `weather` 会被拼成 `https://weather` 导航到 DNS 错误页。归一语义与
 * Windows 端 `url_utils.normalize_url` 对齐（跨端契约）：
 *
 * ① 空输入 → null（拒绝）
 * ② about:blank → 原样放行
 * ③ 带 scheme 前缀：仅 http/https 走 OriginPolicy 校验；file:/javascript:/
 *    data: 等非导航 scheme 一律 null（fail-closed——对齐 Windows P0-1
 *    补丁，杜绝 `https://file:///...` 类 urlparse 盲区）
 * ④ 无 scheme：含空格或不含点号 → 搜索词拼引擎 URL；否则当域名补 https
 * ⑤ 完整 URL 内的空格编码为 %20（浏览器惯例，对齐 Windows D-1 修复）
 *
 * 单源约束：地址栏（SecureNavigator.navigateExternal）与首页搜索框
 * （AegisHomeBridge）共用 normalizeInput，消除双份拼接的语义漂移
 * （首页框旧实现会把 `https://www.baidu.com` 拼成 `https://https://...`）。
 */
object SearchEngines {
    val ENGINE_URLS: Map<String, String> =
        mapOf(
            "baidu" to "https://www.baidu.com/s?wd=",
            "bing" to "https://www.bing.com/search?q=",
            "google" to "https://www.google.com/search?q=",
            "sogou" to "https://www.sogou.com/web?query=",
        )

    const val DEFAULT_ENGINE: String = "baidu"

    /**
     * 首页偏好文件/键单源（全库审计 2026-09-02 收敛）：AegisHomeBridge 与
     * 本对象共用同一 SharedPreferences 文件与引擎键——此前字面量双处硬编码。
     */
    internal const val PREFS_NAME: String = "aegis_home"
    internal const val KEY_ENGINE: String = "engine"

    /** scheme 前缀识别（含 RFC 3986 scheme 字符集，末尾必须有冒号）。 */
    private val SCHEME_PREFIX = Regex("^([a-zA-Z][a-zA-Z0-9+.\\-]*):")

    private val NAV_SCHEMES = setOf("http", "https")

    /** host:port 形态的端口段长度上限（TCP 端口 ≤5 位数字——T1）。 */
    private const val MAX_PORT_SEGMENT_LENGTH = 5

    /** 读取当前搜索引擎 key（与 AegisHomeBridge 同一偏好文件/键——单源）。 */
    fun currentEngine(context: android.content.Context): String =
        context
            .getSharedPreferences(PREFS_NAME, android.content.Context.MODE_PRIVATE)
            .getString(KEY_ENGINE, DEFAULT_ENGINE) ?: DEFAULT_ENGINE

    /** 搜索词拼引擎 URL（Uri.encode 对齐 Windows urllib.parse.quote 语义——`/` 保留）。 */
    fun searchUrl(
        text: String,
        engineKey: String,
    ): String = (ENGINE_URLS[engineKey] ?: ENGINE_URLS[DEFAULT_ENGINE]!!) + Uri.encode(text, "/")

    /**
     * 统一输入归一：地址栏/首页搜索框共用入口。
     * 返回 null 表示拒绝导航（非导航 scheme / 空输入 / 校验失败）。
     */
    fun normalizeInput(
        input: String,
        engineKey: String,
    ): String? =
        when (classifyInput(input)) {
            InputKind.EMPTY, InputKind.FORBIDDEN_SCHEME -> null
            InputKind.ABOUT_BLANK -> "about:blank"
            InputKind.ABSOLUTE_URL -> canonicalizeExternal(input.trim().replace(" ", "%20"))
            InputKind.DOMAIN -> canonicalizeExternal("https://" + input.trim())
            InputKind.SEARCH -> searchUrl(input.trim(), engineKey)
        }

    /** 输入分类（P0-2：纯 JVM 可测——判定与 Android 依赖的拼接分离）。 */
    internal enum class InputKind { EMPTY, ABOUT_BLANK, FORBIDDEN_SCHEME, ABSOLUTE_URL, DOMAIN, SEARCH }

    /**
     * 搜索词 vs 网址判定单源（与 Windows normalize_url 跨端语义一致）：
     * - 空输入 / about:blank 单列
     * - 带 scheme：http/https 为绝对 URL；其余（file:/javascript:/data:
     *   等）FORBIDDEN——fail-closed，绝不补 https:// 拼接
     * - 无 scheme：含空格或不含点号 → 搜索词；否则当域名
     */
    internal fun classifyInput(text: String): InputKind = classifyTrimmed(text.trim())

    private fun classifyTrimmed(trimmed: String): InputKind =
        when {
            trimmed.isEmpty() -> InputKind.EMPTY
            trimmed.equals("about:blank", ignoreCase = true) -> InputKind.ABOUT_BLANK
            else -> classifyWithScheme(trimmed)
        }

    private fun classifyWithScheme(trimmed: String): InputKind {
        val matched =
            SCHEME_PREFIX
                .find(trimmed)
                ?.groupValues
                ?.get(1)
        // T1 修复（全面审计批次2 2026-09-04）：host:port 误杀——SCHEME_PREFIX
        // 会把字母开头的 host（`localhost:8000`、`intranet:80`）匹配成 scheme
        // → FORBIDDEN（开发/内网最高频输入形态被拒）。真 scheme 永不含点
        // （RFC 3986 字母数字+/-）：prefix 含点必为 host → 按 DOMAIN（依
        // looksLikeUrl 保留尾点降级）；prefix 不含点但首个 '/' 前为纯数字
        // 端口段 → host:port 形态直接按 DOMAIN（不能走 looksLikeUrl——
        // 它要求含点，`localhost:8000` 恰好不含点会误降级为 SEARCH）。
        // 其余保持 FORBIDDEN（javascript:/data:/file: 语义不变）。
        return when {
            matched == null -> if (looksLikeUrl(trimmed)) InputKind.DOMAIN else InputKind.SEARCH
            matched.contains('.') -> if (looksLikeUrl(trimmed)) InputKind.DOMAIN else InputKind.SEARCH
            isPortSegment(trimmed.substring(matched.length + 1)) -> InputKind.DOMAIN
            else -> if (matched.lowercase() in NAV_SCHEMES) InputKind.ABSOLUTE_URL else InputKind.FORBIDDEN_SCHEME
        }
    }

    /** T1：host:port 判定——首个 '/' 前为 1-5 位纯数字端口段。 */
    private fun isPortSegment(afterColon: String): Boolean {
        val segment = afterColon.substringBefore('/')
        return segment.isNotEmpty() &&
            segment.length <= MAX_PORT_SEGMENT_LENGTH &&
            segment.all { it.isDigit() }
    }

    private fun looksLikeUrl(text: String): Boolean = !text.contains(' ') && '.' in text && !text.endsWith(".")

    /** D-1 对齐：完整 URL 内空格编码 %20 后再走校验（浏览器惯例）。 */
    internal fun canonicalizeExternal(text: String): String? =
        OriginPolicy
            .tryParseExternal(text.replace(" ", "%20"))
            ?.let(::canonicalize)

    /**
     * A-3 归一（迁移自 BrowserEngine）：https 补前缀 + host 小写化，
     * 对齐 Rust canonicalize_external。完整 URI 重建（path/query/fragment 保留）。
     */
    private fun canonicalize(uri: java.net.URI): String? {
        val host = uri.host?.lowercase() ?: return null
        val port =
            uri.port
                .takeIf { it != -1 }
                ?.let { ":$it" }
                .orEmpty()
        return buildString {
            append(uri.scheme).append("://").append(host).append(port)
            uri.rawPath?.let { append(it) }
            uri.rawQuery?.let { append('?').append(it) }
            uri.rawFragment?.let { append('#').append(it) }
        }
    }
}

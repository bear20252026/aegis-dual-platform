package com.aegis.browser

import android.webkit.WebView
import org.json.JSONTokener

/**
 * 阅读模式（CHANGELOG Planned：Android 阅读模式入口）。
 *
 * 职责：在当前 WebView 页面内提取正文（只读 evaluateJavascript——
 * 不写页面、不经任何桥），产出 ReaderContent 供 Compose 层渲染。
 *
 * 安全边界：
- 提取脚本只读取 DOM 文本（title/innerText），不注入任何宿主对象；
- 结果经 JSONTokener 两段解析（页内脚本返回的是「含 JSON 的字符串」
 的 JSON 表示——防畸形返回崩溃）；
- 正文长度上限 MAX_TEXT（防超长页面拖垮 Compose 渲染）。
 */
data class ReaderContent(
    val title: String,
    val text: String,
)

/**
 * AD-109（审计 2026-09-23 清单·A6 批）：代理对边界回退截断——切点尾部为
 * 高代理（其低代理被切掉）时回退一个 char，不产生孤立代理对。ASCII 文本
 * 行为与 String.take 一致。
 *
 * AD-308（2026-10-02 审计）：自 ReaderMode 成员提升为共享 internal 顶层
 * 函数——LogSanitize.flatten 的截断同有劈代理对面（标题/日志净化口径
 * 单源），MainDialogs 分段（chunkTextAtCharBoundary）注释口径同源。
 */
internal fun takeAtCharBoundary(
    value: String,
    max: Int,
): String {
    if (value.length <= max) return value
    val cut = value.substring(0, max)
    return if (Character.isHighSurrogate(cut.last())) cut.dropLast(1) else cut
}

object ReaderMode {
    /** 正文长度上限（200K 字符——超出截断，防渲染层过载）。 */
    private const val MAX_TEXT = 200_000

    /** AD-227（2026-09-26 审计）：标题截断上限（256——与正文截断同口径，
     *  超长标题此前直进 AlertDialog 标题渲染）。 */
    private const val MAX_TITLE = 256

    /** 认定为「有正文」的最小长度（首页/空白页不进阅读模式）。 */
    private const val MIN_TEXT = 200

    /**
     * 正文提取脚本：优先 article/main/[role=main]，否则取文本量最大
     * 的块级元素，兜底 body。只读，不触碰页面状态。
     * AD-125（审计 2026-09-23 清单·A6 批）：internal 化——MIN_TEXT 门槛在
     * 页内脚本生效，JVM 单测锁定门槛存在性与取值，防误删/漂移。
     *
     * AD-206（审计 2026-09-23 清单·A7 批）：候选块扫描设限提前退出——
     * 原实现对 document.querySelectorAll('div, section') 全量遍历
     * （超长页面数千节点逐个读 innerText——强制布局抖动，主线程可卡
     * 数百 ms）。现设两项限制：①候选上限 MAX_CANDIDATES（400——覆盖
     * 常规文章页全部候选，超出部分不参与正文评选）；②提前退出——
     * 一旦某候选块文本量已达 MAX_TEXT（正文上限），后续候选不可能
     * 更优，立即停止扫描。
     */
    internal val EXTRACT_JS =
        """
        (function() {
          try {
            var node = document.querySelector('article')
              || document.querySelector('main')
              || document.querySelector('[role=main]');
            if (!node) {
              var best = null, bestLen = 0;
              var cand = document.querySelectorAll('div, section');
              var MAX_CANDIDATES = 400;
              var n = cand.length < MAX_CANDIDATES ? cand.length : MAX_CANDIDATES;
              for (var i = 0; i < n; i++) {
                var t = (cand[i].innerText || '').trim();
                if (t.length > bestLen) { bestLen = t.length; best = cand[i]; }
                if (bestLen >= $MAX_TEXT) { break; }
              }
              node = best || document.body;
            }
            var text = ((node && node.innerText) || '').trim();
            return JSON.stringify({
              ok: text.length >= $MIN_TEXT,
              title: (document.title || '').trim(),
              text: text
            });
          } catch (e) { return JSON.stringify({ ok: false }); }
        })();
        """.trimIndent()

    /**
     * 提取当前页面正文（异步——回调在 UI 线程）。
     * onResult 收到 null = 提取失败/无正文（调用方提示，不进阅读模式）。
     */
    fun extract(
        webView: WebView?,
        onResult: (ReaderContent?) -> Unit,
    ) {
        if (webView == null) {
            onResult(null)
            return
        }
        webView.evaluateJavascript(EXTRACT_JS) { raw ->
            onResult(parse(raw))
        }
    }

    /** 两段解析：先还原 JS 返回值（字符串），再解析内层 JSON 对象。
     * AD-028（2026-09-24 审计）：internal 化供 JVM 单测（解析防御边界是安全面）。 */
    internal fun parse(raw: String?): ReaderContent? {
        if (raw.isNullOrBlank()) return null
        return runCatching {
            val value = JSONTokener(raw).nextValue()
            val payload =
                when (value) {
                    is org.json.JSONObject -> value
                    is String -> JSONTokener(value).nextValue() as? org.json.JSONObject
                    else -> null
                } ?: return@runCatching null
            if (!payload.optBoolean("ok", false)) return@runCatching null
            // AD-109（审计 2026-09-23 清单·A6 批）：截断改代理对安全形式——
            // String.take 按UTF-16 char 劈切，切点落在增补字符（emoji 等）
            // 中间会产生孤立代理对（渲染为 � 且 length 语义失真）。
            val text = takeAtCharBoundary(payload.optString("text", ""), MAX_TEXT)
            if (text.isBlank()) return@runCatching null
            ReaderContent(
                // AD-227：title 与 text 同走上限截断（超长标题不进对话框标题）。
                // AD-322（2026-10-02 审计）：空标题兜底迁 UI 层资源单源
                // （ReaderDialog 渲染时取 R.string.reader_mode_title）——
                // 数据层不再硬编码中文。
                title = takeAtCharBoundary(payload.optString("title", ""), MAX_TITLE),
                text = text,
            )
        }.getOrNull()
    }
}

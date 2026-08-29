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

object ReaderMode {
    /** 正文长度上限（200K 字符——超出截断，防渲染层过载）。 */
    private const val MAX_TEXT = 200_000

    /** 认定为「有正文」的最小长度（首页/空白页不进阅读模式）。 */
    private const val MIN_TEXT = 200

    /**
     * 正文提取脚本：优先 article/main/[role=main]，否则取文本量最大
     * 的块级元素，兜底 body。只读，不触碰页面状态。
     */
    private val EXTRACT_JS =
        """
        (function() {
          try {
            var node = document.querySelector('article')
              || document.querySelector('main')
              || document.querySelector('[role=main]');
            if (!node) {
              var best = null, bestLen = 0;
              var cand = document.querySelectorAll('div, section');
              for (var i = 0; i < cand.length; i++) {
                var t = (cand[i].innerText || '').trim();
                if (t.length > bestLen) { bestLen = t.length; best = cand[i]; }
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

    /** 两段解析：先还原 JS 返回值（字符串），再解析内层 JSON 对象。 */
    private fun parse(raw: String?): ReaderContent? {
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
            val text = (payload.optString("text", "")).take(MAX_TEXT)
            if (text.isBlank()) return@runCatching null
            ReaderContent(
                title = payload.optString("title", "").ifBlank { "阅读模式" },
                text = text,
            )
        }.getOrNull()
    }
}

package com.aegis.browser

import android.webkit.WebView
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 页面功能控制器：阅读模式 + 整页翻译入口（单文件单职责）。
 *
 * 职责边界：持有「阅读/翻译」两个页面级功能的状态与动作；不直接
 * 拥有 TabManager——经构造回调访问当前 WebView/URL 与安全导航，
 * 保持与 BrowserViewModel 的单向依赖（INV-04：状态仍以 StateFlow
 * 经 ViewModel 层暴露给 Compose，UI 不持有浏览器状态）。
 *
 * 安全边界（不变）：
 * - 阅读提取只读 evaluateJavascript（见 [ReaderMode]）；
 * - 翻译导航仍经 SecureNavigator.navigateExternal（http/https 白名单
 *   + Broker 授权），且 URL 外发翻译服务 = 用户显式点击触发。
 */
class ReaderController internal constructor(
    private val currentWebView: () -> WebView?,
    private val currentUrl: () -> String?,
    private val navigateExternal: (String) -> Boolean,
    // AD-228（2026-09-26 审计）：两条提示此前硬编码中文（AD-045/046 迁移
    // 漏网）——经资源 id 回调上抛，文案收敛 strings.xml 单源（原裸字符串
    // alert 回调随最后两个调用点一并移除）。
    private val alertRes: (Int) -> Unit = {},
) {
    private val _content = MutableStateFlow<ReaderContent?>(null)
    val content: StateFlow<ReaderContent?> = _content.asStateFlow()

    /**
     * 阅读模式：提取当前标签正文（异步回填 [content]）。
     *
     * AD-267（2026-10-01 审计）：evaluateJavascript 回填做归属校验——提取发起
     * 后用户切标签，异步回调落地时 [currentWebView] 已不是发起时的 WebView：
     * 旧正文不得写入新语境（闭包比对发起时 WebView 与当前 WebView 实例一致
     * 才回填/提示）。
     */
    fun toggleReaderMode() {
        val originWebView = currentWebView()
        ReaderMode.extract(originWebView) { extracted ->
            if (currentWebView() !== originWebView) {
                // 提取期间已切换标签——丢弃过期正文（不提示：新标签语境下
                // 弹「无正文」同样错位）
                return@extract
            }
            if (extracted == null) {
                alertRes(R.string.reader_no_content)
            } else {
                _content.value = extracted
            }
        }
    }

    /** 关闭阅读模式对话框。 */
    fun dismissReader() {
        _content.value = null
    }

    /** 整页翻译入口：当前页包装为翻译服务地址后走安全导航。 */
    fun translateCurrentPage() {
        val target = TranslateEntry.buildUrl(currentUrl())
        val navigated = target != null && navigateExternal(target)
        if (!navigated) {
            alertRes(R.string.translate_unavailable)
        }
    }
}

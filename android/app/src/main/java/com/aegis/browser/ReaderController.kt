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
    private val alert: (String) -> Unit,
) {
    private val _content = MutableStateFlow<ReaderContent?>(null)
    val content: StateFlow<ReaderContent?> = _content.asStateFlow()

    /** 阅读模式：提取当前标签正文（异步回填 [content]）。 */
    fun toggleReaderMode() {
        ReaderMode.extract(currentWebView()) { extracted ->
            if (extracted == null) {
                alert("当前页面没有可提取的正文")
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
            alert("当前页面无法翻译或未通过安全策略验证")
        }
    }
}

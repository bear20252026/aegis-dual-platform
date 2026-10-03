package com.aegis.browser

import com.aegis.broker.ApprovalRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 拆分批（2026-10-03 剩余项批）：BrowserViewModel 的「安全提示 + 导航审批 +
 * 下载确认」三块内聚状态与操作单文件——原内嵌于 BrowserViewModel（将文件
 * 顶出改造红线 500 行）。以显式 lambda 接缝持有宿主能力（AD-103 的
 * BrowserViewModelHost 同款模式）：保持 BrowserViewModel 公开委托签名不变
 * （detekt 基线签名/JVM 单测零改动），接缝成员不外泄公开 API。
 *
 * 状态归属不变式（与原实现逐行等价）：
 * - [webViewAlert] 单槽：一般安全提示（SECURITY_NOTICE）与版本检查提示
 *   （VERSION_CHECK）分型共用（原 :124 注释口径）；
 * - [pendingNavigationConfirmation] 单写点 = [registerPendingConfirmation]
 *   （仅 ViewModel 保存发起 WebView 引用——AD-158 internal 化供 JVM 单测）；
 * - [pendingDownloadConfirmation] 批准即续体单次调用（AD-331，重复点击
 *   /dialog 复现均为 no-op）。
 */
// TooManyFunctions 豁免（BrowserViewModelHost 的 LongParameterList 同款先例）：
// 「提示 + 双确认流」是单职责内聚块——13 个函数全部围绕三个单槽 StateFlow
// 的登记/撤销/分型文案，拆分反而引入状态对象间接层。
@Suppress("TooManyFunctions")
internal class BrowserViewModelConfirmations(
    /** 审批归属校验缝：只允许当前活动标签的 WebView 消费授权（防错标）。 */
    private val currentWebView: () -> android.webkit.WebView?,
    /** AD-046：提示文案经资源单源（init 后 appContext 必然可用）。 */
    private val resolveText: (Int) -> String,
    private val resolveTextWithArg: (Int, String) -> String = { _, _ -> "" },
) {
    private val _webViewAlert = MutableStateFlow<WebViewAlertNotice?>(null)
    val webViewAlert: StateFlow<WebViewAlertNotice?> = _webViewAlert.asStateFlow()

    private val _pendingNavigationConfirmation =
        MutableStateFlow<PendingNavigationConfirmation?>(null)
    val pendingNavigationConfirmation: StateFlow<PendingNavigationConfirmation?> =
        _pendingNavigationConfirmation.asStateFlow()

    private val _pendingDownloadConfirmation =
        MutableStateFlow<PendingDownloadConfirmation?>(null)
    val pendingDownloadConfirmation: StateFlow<PendingDownloadConfirmation?> =
        _pendingDownloadConfirmation.asStateFlow()

    /** 一般安全提示（单按钮「知道了」——AD-258 分型口径）。 */
    fun setWebViewAlert(message: String?) {
        _webViewAlert.value =
            message?.let { WebViewAlertNotice(it, WebViewAlertNotice.Kind.SECURITY_NOTICE) }
    }

    /** AD-260：版本检查提示（双按钮「去更新/稍后」——与一般提示分型）。 */
    fun setWebViewVersionAlert(message: String) {
        _webViewAlert.value = WebViewAlertNotice(message, WebViewAlertNotice.Kind.VERSION_CHECK)
    }

    /** AD-046/260：一般安全提示构造单点（文案 + SECURITY_NOTICE 分型）。 */
    fun setSecurityNotice(id: Int) {
        _webViewAlert.value = WebViewAlertNotice(resolveText(id), WebViewAlertNotice.Kind.SECURITY_NOTICE)
    }

    /** 页面错误/提示文案缝（pageErrorStringsOf 注入面——含带参重载）。 */
    fun alertText(id: Int): String = resolveText(id)

    /** 带参文案缝（AD-258 类占位符——pageErrorStringsOf 第二缝）。 */
    fun alertText(
        id: Int,
        arg: String,
    ): String = resolveTextWithArg(id, arg)

    /**
     * Compose 的明确批准操作。只允许当前活动标签的待审批请求恢复导航，
     * 防止标签切换后在错误 WebView 上消费授权；客户端仍会在恢复前调用
     * Rust 核心批准并消费。
     */
    fun approvePendingNavigationConfirmation(): Boolean {
        val pending = _pendingNavigationConfirmation.value
        if (pending == null || currentWebView() !== pending.webView) {
            if (pending != null) setSecurityNotice(R.string.confirm_switch_back)
            return false
        }
        _pendingNavigationConfirmation.value = null
        val approved =
            SecureWebViewFactory
                .navigatorFor(pending.webView)
                ?.approvePendingNavigation() == true
        if (!approved) setSecurityNotice(R.string.confirm_invalid)
        return approved
    }

    /** 对话框关闭、返回键或拒绝按钮一律走此入口；失败不会恢复导航。 */
    fun rejectPendingNavigationConfirmation(): Boolean {
        val pending = _pendingNavigationConfirmation.value ?: return false
        _pendingNavigationConfirmation.value = null
        return SecureWebViewFactory.navigatorFor(pending.webView)?.rejectPendingNavigation() == true
    }

    /**
     * AD-331（2026-10-02 审计）：下载确认对话框「仍要下载」——仅消费当前
     * 挂起项一次（批准后清除，续体单次调用；重复点击/dialog 复现均为 no-op）。
     */
    fun approvePendingDownload() {
        val pending = _pendingDownloadConfirmation.value ?: return
        _pendingDownloadConfirmation.value = null
        pending.proceed()
    }

    /** AD-331：下载确认对话框拒绝/关闭——放弃待确认下载（fail-closed）。 */
    fun rejectPendingDownload() {
        _pendingDownloadConfirmation.value = null
    }

    /** 仅 ViewModel 保存发起 WebView 引用（PendingNavigationConfirmation 单写点）。
     *  AD-158 配套：internal 化供 JVM/Robolectric 单测注入待审批状态。 */
    fun registerPendingConfirmation(
        webView: android.webkit.WebView,
        request: ApprovalRequest,
    ) {
        _pendingNavigationConfirmation.value = PendingNavigationConfirmation(webView, request)
    }

    /** 待审批解除：仅当解除请求来自挂起请求自身（幂等防错标）。 */
    fun resolvePendingConfirmation(webView: android.webkit.WebView) {
        if (_pendingNavigationConfirmation.value?.webView === webView) {
            _pendingNavigationConfirmation.value = null
        }
    }

    /** AD-331 装配缝：由 WebViewDownloadHandler 经 hostImpl 上抛登记（单槽）。 */
    fun registerPendingDownload(
        webView: android.webkit.WebView,
        url: String,
        proceed: () -> Unit,
    ) {
        _pendingDownloadConfirmation.value =
            PendingDownloadConfirmation(webView = webView, url = url, continuation = proceed)
    }

    /** 下载待确认按 WebView 归属撤销（closeTab 关闭对应标签时——幂等）。 */
    fun resolvePendingDownload(webView: android.webkit.WebView) {
        if (_pendingDownloadConfirmation.value?.webView === webView) {
            _pendingDownloadConfirmation.value = null
        }
    }
}

package com.aegis.browser

/**
 * AD-103/A7 批（审计 2026-09-23 清单·A7 批）：BrowserViewModel 的
 * WebViewEventAssembly.Host 接缝实现单文件——原 hostImpl 匿名 object 与
 * pageErrorStrings 内嵌在 BrowserViewModel 尾部（将文件顶出改造红线 500 行）。
 * 以显式 lambda 接缝持有宿主能力：保持 BrowserViewModel 公开父类签名不变
 * （detekt 基线签名稳定）且接缝成员不外泄公开 API（AD-103 语义不变）。
 *
 * init 前回调安全降级（tabManagerOrNull 返回 null——与 AD-103 同口径）。
 *
 * LongParameterList 豁免（与 AddressBarRow 同口径）：9 个参数全部是
 * Host 接缝的回调装配点——拆分反而引入状态对象间接层（AD-103 原注）。
 */
@Suppress("LongParameterList")
internal class BrowserViewModelHost(
    private val tabManagerOrNull: () -> TabManager?,
    private val addressDraftActive: () -> Boolean,
    private val mapDisplayAddress: (String) -> String,
    // AD-003 回归（2026-09-29）：回调属性加 on 前缀——原名与 override 方法
    // 同名（submitPageAddress/clearPageError 等 5 处），override 体内的裸
    // 调用经 Kotlin 重载解析命中**成员函数自身**（函数优先于属性 invoke
    // 约定）→ 无限自递归 StackOverflowError。debug 下因触发路径未被走查
    // 潜伏；R8 真机回归（AD-003）启动期即实锤。改名消除名字遮蔽。
    private val onSubmitPageAddress: (String) -> Unit,
    private val onSubmitPageError: (PageError) -> Unit,
    private val onClearPageError: () -> Unit,
    private val onSubmitWebViewAlert: (String) -> Unit,
    private val onRefreshTabs: () -> Unit,
    // AD-332 回归修复（2026-10-02 审计）：属性改 resolveErrorStrings——原名与
    // override fun errorStrings() 同名，override 体内裸调用与 AD-003 同型
    // （同名成员函数优先于属性 invoke 约定 → 无限自递归 SOE 风险；本文件
    // 头部 AD-003 注记同款）。改名消除名字遮蔽，override 委托真属性。
    private val resolveErrorStrings: () -> PageErrorTexts.Strings,
    // AD-331（2026-10-02 审计）：二级下载确认上抛（ViewModel 单写点登记
    // PendingDownloadConfirmation——MainDialogs 单槽渲染）。
    private val onRequestDownloadConfirmation:
        (android.webkit.WebView, String, () -> Unit) -> Unit = { _, _, _ -> },
) : WebViewEventAssembly.Host {
    override val activeTabManager: TabManager?
        get() = tabManagerOrNull()

    override val isAddressDraftActive: Boolean
        get() = addressDraftActive()

    override fun displayAddress(url: String): String = mapDisplayAddress(url)

    override fun submitPageAddress(url: String) {
        onSubmitPageAddress(url)
    }

    override fun submitPageError(error: PageError) {
        onSubmitPageError(error)
    }

    override fun clearPageError() {
        onClearPageError()
    }

    override fun submitWebViewAlert(text: String) {
        onSubmitWebViewAlert(text)
    }

    override fun refreshTabs() {
        onRefreshTabs()
    }

    override fun errorStrings(): PageErrorTexts.Strings = resolveErrorStrings()

    override fun requestDownloadConfirmation(
        webView: android.webkit.WebView,
        url: String,
        proceed: () -> Unit,
    ) {
        onRequestDownloadConfirmation(webView, url, proceed)
    }
}

/**
 * 错误文案解析接缝（appContext getString 函数化——AD-046 单源）。
 * Strings 双方法重载无法 SAM——object 表达式在此单点构造。
 */
internal fun pageErrorStringsOf(
    text: (Int) -> String,
    textWithArg: (Int, String) -> String,
): PageErrorTexts.Strings =
    object : PageErrorTexts.Strings {
        override fun text(id: Int): String = text(id)

        override fun text(
            id: Int,
            arg: String,
        ): String = textWithArg(id, arg)
    }

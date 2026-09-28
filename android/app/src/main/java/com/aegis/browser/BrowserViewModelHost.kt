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
    private val submitPageAddress: (String) -> Unit,
    private val submitPageError: (PageError) -> Unit,
    private val clearPageError: () -> Unit,
    private val submitWebViewAlert: (String) -> Unit,
    private val refreshTabs: () -> Unit,
    private val errorStrings: () -> PageErrorTexts.Strings,
) : WebViewEventAssembly.Host {
    override val activeTabManager: TabManager?
        get() = tabManagerOrNull()

    override val isAddressDraftActive: Boolean
        get() = addressDraftActive()

    override fun displayAddress(url: String): String = mapDisplayAddress(url)

    override fun submitPageAddress(url: String) {
        submitPageAddress(url)
    }

    override fun submitPageError(error: PageError) {
        submitPageError(error)
    }

    override fun clearPageError() {
        clearPageError()
    }

    override fun submitWebViewAlert(text: String) {
        submitWebViewAlert(text)
    }

    override fun refreshTabs() {
        refreshTabs()
    }

    override fun errorStrings(): PageErrorTexts.Strings = errorStrings()
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

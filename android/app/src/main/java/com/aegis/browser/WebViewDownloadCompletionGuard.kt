package com.aegis.browser

/**
 * 下载**完成后**对最终地址的复判（R9-AD-3 / 队列 Q3，第九轮 2026-10-13）。
 *
 * 要补的洞很具体：[WebViewDownloadHandler] 的形态闸门判的是**入队时那个 URL**，而实际
 * 取数据的是另一个进程里的系统 DownloadProvider，它默认**跟随重定向**（全树零
 * `setRedirectsAllowed(false)`）⇒ `https://ok.example/a` 一发 302 指到
 * `http://169.254.169.254/latest/meta-data/`，闸门从未看到那个落点，文件就落进公共
 * 下载目录。这正是 PR #130（R8-AD-03 下载层保留地址硬拒）消除过的后果的复活路径，
 * 只是换了个入口。
 *
 * 修法取「复判 + 撤销 + 留痕」而不是 `setRedirectsAllowed(false)`：后者会打断一切正当
 * CDN 重定向（产品代价，登记时已否决）。DownloadProvider 跟随重定向后会把 `COLUMN_URI`
 * 更新成**实际取到数据的那个 URI**，所以完成后查这一列，就拿到了闸门本该看到的输入。
 *
 * 判据**不新造一份**：地址判定直接复用 [WebViewDownloadTargetGuard.rejectionOf]——同一张
 * 段表、同一个拒绝码、同一条「本机与内网必须能打开」的上界（B8 裁决）。为「重定向落点」
 * 另写一条判定＝第二个判据源，而各抄一份正是本仓反复登记的病。
 */
internal object WebViewDownloadCompletionGuard {
    /**
     * 纯判定（零 Android 类型 ⇒ JVM 可测）：命中拦截 ⇒ 返回「脱敏留痕文本 to 文案资源 id」，
     * 放行 ⇒ null。`finalScheme` 由接线侧从查询到的 URI 现取——与入队侧同一口径，
     * `android.net.Uri` 只出现在接线侧，本仓不欢迎第二个 URL 解析器。
     *
     * 「读不到最终 URI」⇒ **不删**（返回 null）：查询失败、记录不属于本应用、行里没这几列
     * 这几种输入下，删用户的文件是把「判据无从判断」转嫁成产品故障。不扩成「读不到就拦」，
     * 因为对已落盘的东西「拦」的唯一手段就是删，而删不可逆。
     */
    fun verdict(
        finalUrl: String?,
        finalScheme: String?,
    ): Pair<String, Int>? {
        if (finalUrl.isNullOrBlank()) return null
        return WebViewDownloadTargetGuard.rejectionOf(finalUrl, finalScheme)
    }

    /** 只有**成功完成**的记录值得复判——状态非 SUCCESSFUL 时没有已落盘的文件需要撤销。 */
    fun shouldRejudge(status: Int?): Boolean = status == DOWNLOAD_STATUS_SUCCESSFUL

    /**
     * 行级判定（接线侧一次调用）：先判状态再判地址——顺序即优先级，
     * 「下载没成功」时不得弹「已拦截指向保留地址的下载」这种与实际不符的话。
     */
    fun rowVerdict(
        status: Int?,
        finalUrl: String?,
        finalScheme: String?,
    ): Pair<String, Int>? {
        if (!shouldRejudge(status)) return null
        return verdict(finalUrl, finalScheme)
    }
}

/**
 * 与 `DownloadManager.STATUS_SUCCESSFUL` 同值（该公开常量自 API 9 起就是这个数）。
 * 写成这里的一个常量是为了让「状态判据」在 JVM 侧可断言——用例同时拿平台常量对账，
 * 所以这不是一个手抄的魔数，而是一条有锚的等式。
 */
internal const val DOWNLOAD_STATUS_SUCCESSFUL = 8

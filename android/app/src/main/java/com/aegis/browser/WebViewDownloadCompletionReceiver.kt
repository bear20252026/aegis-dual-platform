package com.aegis.browser

import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.database.Cursor
import android.widget.Toast
import com.aegis.webviewadapter.LogRedact

/**
 * 下载完成后的复判接线（R9-AD-3 / 队列 Q3，第九轮 2026-10-13）。
 *
 * 把 DownloadProvider **实际取数的那个 URI**（跟随重定向后被更新的 `COLUMN_URI`）交回
 * [WebViewDownloadCompletionGuard] 复判；命中即 `remove()` 撤销已落盘的文件并留痕。
 * 入队侧的 [WebViewDownloadHandler] 只看得到入队 URL，这条补的是它对重定向落点的盲区
 * ——系统 DownloadProvider 在另一个进程，本 app 的 `network_security_config.xml` 管不到它。
 *
 * 为什么是 manifest receiver 而不是运行时 `registerReceiver`：DownloadManager 的完成
 * 广播只投递给发起下载的那个包（系统按归属定投），所以 `exported="false"` 就收得到；
 * 反过来 exported=true 等于把「任意应用伪造一个 download_id 让本 app 删自己的文件」
 * 开放出去。
 *
 * 平台事实的诚实边界：`COLUMN_URI` 等于「重定向后的最终地址」依据的是 AOSP
 * `AbstractDownloadThread.redirect()` 把 URI 列改写成跳转目标这一行为，本仓**无设备实证**，
 * 所以这条链的验收步已写进 `docs/runbooks/device-validation.md` Android 第 8 步。
 * 若某 ROM 不改写该列，本复判只是拿不到新信息（判据返回 null ⇒ 不删），不会误删正当下载。
 */
class WebViewDownloadCompletionReceiver : BroadcastReceiver() {
    override fun onReceive(
        context: Context,
        intent: Intent?,
    ) {
        val downloadId = completedDownloadId(intent) ?: return
        val manager = context.getSystemService(DownloadManager::class.java) ?: return
        retireIfLandingBlocked(context, manager, downloadId)
    }

    /**
     * 「本 app 的一次下载完成了」这件事的两个必要条件合在一处判：action 对得上，
     * 且带回了合法 id（真实 id 从 1 起，负值是缺省哨兵）。合成一个函数除了收敛
     * 入口的 return 数，更重要的是这两条本就是一件事——拆开写迟早只改一头。
     */
    private fun completedDownloadId(intent: Intent?): Long? {
        if (intent?.action != DownloadManager.ACTION_DOWNLOAD_COMPLETE) return null
        val id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, NO_DOWNLOAD_ID)
        return if (id == NO_DOWNLOAD_ID) null else id
    }

    private fun retireIfLandingBlocked(
        context: Context,
        manager: DownloadManager,
        downloadId: Long,
    ) {
        val row = queryRow(manager, downloadId)
        val rejection =
            WebViewDownloadCompletionGuard.rowVerdict(row?.status, row?.url, row?.scheme) ?: return
        android.util.Log.w(
            TAG,
            "下载完成复判命中（入队地址经重定向落到被拦地址）: ${LogRedact.redact(row?.url ?: "")} " +
                "判据留痕=${rejection.first}",
        )
        val removed = runCatching { manager.remove(downloadId) }
        if (removed.isFailure) {
            // 撤销失败＝文件仍在公共下载目录。这种输入下说不出「已拦截」，只在日志里记实。
            android.util.Log.e(
                TAG,
                "复判命中但撤销下载失败（文件仍在公共目录，需人工删除）: ${removed.exceptionOrNull()?.message}",
            )
        }
        Toast.makeText(context, context.getString(rejection.second), Toast.LENGTH_LONG).show()
    }

    /**
     * 读那一行：状态 + URI + URI 的 scheme。任何一环读不到就交 null 给判据
     * （[WebViewDownloadCompletionGuard.verdict] 的「无从判断 ⇒ 不删」口径）；查询本身
     * 抛异常只留一条告警，绝不让广播处理崩掉。scheme 由 `android.net.Uri` 现取——与
     * 入队侧同一个解析器，判据面里不出现第二份 URL 解析。
     */
    private fun queryRow(
        manager: DownloadManager,
        downloadId: Long,
    ): Row? {
        val query = DownloadManager.Query().setFilterById(downloadId)
        return runCatching {
            val cursor = manager.query(query)
            cursor?.use { rowOf(it) }
        }.onFailure {
            android.util.Log.w(TAG, "下载完成复判查询失败: ${it.javaClass.name}")
        }.getOrNull()
    }

    private fun rowOf(cursor: Cursor): Row? {
        val url = if (cursor.moveToFirst()) cursor.stringValue(DownloadManager.COLUMN_URI) else null
        if (url.isNullOrEmpty()) return null
        // 与入队侧同一形状取 scheme（ktlint 的 chain-method-continuation 要求限定名
        // 接收者的链每一环都断行；这里照抄通过 CI 的那份写法，不另立风格）。
        // 取不出 scheme 时**不豁免**——入队闸门对同样的输入本来就判「非 http(s) 拦」，
        // 复判在这里改成放行就是第二套口径（用例 rejudgeUsesTheEnqueueGateVerbatim 钉着）。
        val scheme =
            android.net.Uri
                .parse(url)
                .scheme
                ?.lowercase()
        val status = cursor.intValue(DownloadManager.COLUMN_STATUS)
        return Row(status, url, scheme)
    }

    private fun Cursor.intValue(column: String): Int? {
        val index = getColumnIndex(column)
        return if (index < 0 || isNull(index)) null else getInt(index)
    }

    private fun Cursor.stringValue(column: String): String? {
        val index = getColumnIndex(column)
        return if (index < 0 || isNull(index)) null else getString(index)
    }

    /** 一行下载记录里判据需要的三样东西（读不到就是 null，交给判据决定）。 */
    private data class Row(
        val status: Int?,
        val url: String?,
        val scheme: String?,
    )

    companion object {
        private const val TAG = "AegisDownload"

        /** `EXTRA_DOWNLOAD_ID` 的缺省哨兵——用它区分「广播没带 id」。 */
        private const val NO_DOWNLOAD_ID = -1L
    }
}

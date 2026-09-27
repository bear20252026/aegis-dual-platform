package com.aegis.browser

import android.webkit.WebView
import com.aegis.webviewadapter.AegisWebViewClient

/**
 * 受控导航器（单文件单职责：从 SecureWebViewFactory 拆出）。
 * 将 URL 规范化、Broker 授权和 WebView 副作用收敛到单一路径。
 */
class SecureNavigator internal constructor(
    private val webView: WebView,
    private val client: AegisWebViewClient,
) {
    companion object {
        /**
         * 画板受信资产路径（AD-148，审计 2026-09-23 清单·A6 批：单源常量
         * ——AegisHomeBridge.openGeogebra 此前双处硬编码同一路径字面量，
         * 白名单改路径时漏改即静默拒绝，现引用本常量）。
         */
        internal const val GEOGEBRA_ASSET_PATH = "geogebra/GeoGebra/HTML5/5.0/GeoGebra.html"

        /** 内置受信资产白名单（H-5：第一方资源，路径编译期固定）。 */
        private val TRUSTED_ASSET_PATHS =
            setOf(
                GEOGEBRA_ASSET_PATH,
            )
    }

    fun openTrustedHome() {
        webView.loadUrl(BrowserEngine.HOME_URL)
    }

    /**
     * H-5 修复（审计 2026-08-31）：内置受信资产加载收敛到导航器单一路径。
     * 常量白名单校验——仅放行编译期固定的第一方 assets 资源（与
     * openTrustedHome 同信任级：file:// 不经 Broker，但路径不可被调用方
     * 控制）；白名单外一律拒绝。桥接层不得直接持有 webView.loadUrl。
     *
     * WB-106（2026-09-26 审计）：[isTrustedAsset] 抽出白名单谓词——桥接层
     * 在 JS 后台线程先行同步判定加载受理结果（loadUrl 主线程投递照旧），
     * openGeogebra 透传受理结果而非恒返回 webView 非空。
     */
    fun openTrustedAsset(assetPath: String): Boolean {
        if (!isTrustedAsset(assetPath)) return false
        webView.loadUrl("file:///android_asset/$assetPath")
        return true
    }

    /** WB-106：受信资产白名单判定（与 [openTrustedAsset] 同一谓词——线程安全）。 */
    internal fun isTrustedAsset(assetPath: String): Boolean = assetPath in TRUSTED_ASSET_PATHS

    fun navigateExternal(input: String): Boolean {
        // P0-2 修复（搜索审计 2026-09-01）：归一走 SearchEngines 单源并传
        // 当前引擎 key——地址栏输入搜索词拼搜索引擎 URL（此前被当主机名
        // 拼成 https://<搜索词> 导航到 DNS 错误页）
        val engineKey = SearchEngines.currentEngine(webView.context)
        val normalized = BrowserEngine.normalizeExternal(input, engineKey) ?: return false
        return client.navigate(webView, normalized)
    }

    /** 仅由受信 Compose chrome 的明确批准操作调用；客户端仍负责 Rust 批准与 nonce 消费。 */
    fun approvePendingNavigation(): Boolean = client.approvePendingNavigation(webView)

    /** 对话框关闭、拒绝、标签关闭或生命周期销毁时撤销待审批导航。 */
    fun rejectPendingNavigation(): Boolean = client.rejectPendingNavigation()

    fun navigateHistory(action: HistoryAction): Boolean =
        when (action) {
            HistoryAction.BACK -> {
                webView.canGoBack().also { if (it) webView.goBack() }
            }

            HistoryAction.FORWARD -> {
                webView.canGoForward().also { if (it) webView.goForward() }
            }

            HistoryAction.RELOAD -> {
                webView.reload()
                true
            }
        }

    fun close() {
        client.close()
    }
}

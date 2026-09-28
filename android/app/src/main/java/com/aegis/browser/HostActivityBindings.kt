package com.aegis.browser

import android.app.Activity
import java.util.concurrent.atomic.AtomicBoolean

/**
 * AD-103 配套（审计 2026-09-23 清单·A6 批）：宿主 Activity 绑定与 WebView
 * 版本检查去重的独立小类——自 BrowserViewModel 抽出（弱引用持有/可用性
 * 判定/进程级检查去重是自洽的内聚块，抽出后 ViewModel 行数回到改造
 * 红线内）。
 *
 * - 宿主引用：P0-5 修复（全面审计 2026-09-04）——P0-6 崩溃重建需要主题化
 *   Activity context 创建 WebView；onDestroy 且 isFinishing 时 detach。
 *   @Volatile：写入仅在主线程生命周期回调，读可能来自渲染崩溃回调链。
 * - 版本检查去重：AD-239（2026-09-26 审计）——未声明 configChanges 的变更
 *   触发 Activity 重建后不得再次弹提示；AtomicBoolean 防重建间隙并发重复
 *   放行（ViewModel 存续于重建，标记进程内单次）。
 */
internal class HostActivityBindings {
    @Volatile
    private var ref: java.lang.ref.WeakReference<Activity>? = null

    private val webviewVersionCheckStarted = AtomicBoolean(false)

    /** MainActivity onCreate 注入宿主引用（弱引用，不阻止 Activity GC）。 */
    fun attach(activity: Activity) {
        ref = java.lang.ref.WeakReference(activity)
    }

    /** isFinishing 销毁时解除引用；配置变更重建绝不 detach（新 Activity 重新 attach）。 */
    fun detach() {
        ref = null
    }

    /** 可用的宿主 Activity（已 finish/destroy 的引用视为不可用，返回 null）。 */
    fun availableOrNull(): Activity? {
        val candidate = ref?.get() ?: return null
        return candidate.takeUnless { it.isFinishing || it.isDestroyed }
    }

    /** AD-239：版本检查单次触发（结果与提示跨 Activity 重建不重复）。 */
    fun checkWebViewVersionOnce(
        context: android.content.Context?,
        onOutdated: (String) -> Unit,
    ) {
        if (context == null) return
        if (!webviewVersionCheckStarted.compareAndSet(false, true)) return
        WebViewVersionCheck.checkAndPrompt(context, onOutdated)
    }
}

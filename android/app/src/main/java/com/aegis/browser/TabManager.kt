package com.aegis.browser

import android.os.SystemClock
import android.webkit.WebView

/**
 * 标签管理器（单文件单职责：多标签的增删、切换与挂起恢复）。
 *
 * 设计要点：
 * 1. 每个标签持有独立 WebView —— 切换时只改变显示/隐藏，不销毁页面，
 *    保留各标签的滚动位置、表单状态与前进后退历史（商业浏览器行为）。
 * 2. 活跃标签上限 [maxActive]（默认 8）：新增标签超过上限时，挂起
 *    最旧的非活跃标签（释放 WebView 绘制资源）；切回时自动恢复。
 *    挂起/恢复动作通过 [pause] / [resume] 函数注入，默认调用 WebView
 *    自带 onPause()/onResume()，便于单测时注入假实现。
 * 3. 索引操作全部做边界校验：越界静默拒绝（返回 null / false），
 *    绝不让 UI 层因索引越界崩溃。
 * 4. AD-084（2026-09-26 审计）：[Tab] 字段全部 val——本类是唯一写路径，
 *    所有状态变更经 copy 替换列表内实例（StateFlow 依赖 equals 感知变化）。
 *
 * 本类不依赖任何 UI（Compose/Activity），可离线单测。
 */
@Suppress("TooManyFunctions") // AD-036 新增 updateUrl 触发阈值（11）——多标签管理内聚职责
class TabManager(
    private val maxActive: Int = 8,
    private val pause: (WebView) -> Unit = WebView::onPause,
    private val resume: (WebView) -> Unit = WebView::onResume,
) {
    // AD-322（2026-10-02 审计）：DEFAULT_TAB_TITLE 硬编码中文已迁 R.string
    //（UI 层渲染兜底——TabChipCore 空标题取 stringResource(tab_default_title)）。
    // 数据层默认标题为空串：本地化是展示职责，数据层只承载状态。

    private val tabs = mutableListOf<Tab>()
    private var nextId = 0L

    /** 当前激活标签的索引；无标签时为 -1。 */
    var activeIndex: Int = -1
        private set

    /** 标签总数。 */
    val size: Int
        get() = tabs.size

    /** 新增标签并激活。返回新标签（id 由管理器分配）。 */
    fun addTab(
        webView: WebView,
        url: String = "",
        title: String = "",
    ): Tab {
        tabs +=
            Tab(
                id = nextId++,
                title = title,
                url = url,
                webView = webView,
                lastUsed = SystemClock.elapsedRealtime(),
            )
        // 挂起旧标签，保证活跃标签数不超过上限（LRU：优先最久未用）
        suspendOldestBeyondLimit()
        switchTo(tabs.size - 1)
        // AD-084：switchTo 经 copy 替换实例——返回列表内规范实例（而非构造
        // 瞬间快照），保证调用方持有引用与后续 list()/current() 一致。
        return tabs.last()
    }

    /** 切换到指定标签并恢复其 WebView；越界返回 false。 */
    fun switchTo(index: Int): Boolean {
        if (index !in tabs.indices) return false
        // 挂起上一个激活标签（若不同且尚未挂起）
        val prevIndex = activeIndex
        if (prevIndex >= 0 && prevIndex != index) {
            val prev = tabs[prevIndex]
            if (!prev.suspended) {
                pause(prev.webView)
                tabs[prevIndex] = prev.copy(suspended = true)
            }
        }
        // 恢复目标标签并更新 LRU 时间戳（落地③：多标签性能优化）
        val target = tabs[index]
        if (target.suspended) {
            resume(target.webView)
        }
        tabs[index] = target.copy(suspended = false, lastUsed = SystemClock.elapsedRealtime())
        activeIndex = index
        return true
    }

    /**
     * 关闭指定标签；越界或仅剩 1 个返回 false。
     *
     * AD-254（2026-10-01 审计）：激活位按 index 与 activeIndex 关系分支——
     * 原实现一律 `activeIndex = index`，关闭后台标签也把激活位切到被关位置
     * （激活跳变 + 双活跃 WebView：原激活标签未被 pause，接管标签又被
     * resume）。现在：
     * - index > activeIndex：关闭的是激活标签之后的后台标签，激活位不动；
     * - index < activeIndex：前方移除使后续标签左移，激活位同移一位（同一标签）；
     * - index == activeIndex：关闭的是激活标签本身，相邻标签接管
     *   （min(index, size-1)），接管标签挂起态时 resume——此时原激活标签
     *   已随移除路径 pause + tearDown（原激活标签非 current 时 pause 的
     *   单点即 [pause]（removed.webView））。
     */
    fun closeTab(index: Int): Boolean {
        if (index !in tabs.indices) return false
        if (tabs.size <= 1) return false // 保留至少一个标签（浏览器约定）
        val removed = tabs.removeAt(index)
        pause(removed.webView) // 释放被关闭 WebView 的绘制资源
        // H-4 修复（审计 2026-08-31）：统一销毁序列（停载/摘除/注销/destroy 单源）
        SecureWebViewFactory.tearDown(removed.webView)
        when {
            index > activeIndex -> {
                Unit
            }

            // 后方后台标签：激活位不变
            index < activeIndex -> {
                activeIndex -= 1
            }

            // 前方移除：激活标签左移一位
            else -> {
                // 关闭激活标签：相邻标签接管并恢复（挂起态时）
                activeIndex = minOf(index, tabs.size - 1)
                current()?.let { current ->
                    if (current.suspended) {
                        resume(current.webView)
                        tabs[activeIndex] = current.copy(suspended = false)
                    }
                }
            }
        }
        return true
    }

    /** 当前激活标签；无标签时返回 null。 */
    fun current(): Tab? = tabs.getOrNull(activeIndex)

    /**
     * P1-3 修复（全量复审 2026-09-01）：渲染进程崩溃后原位替换 WebView。
     * 保留标签 id/标题/挂起状态，返回旧 WebView（清理由调用方负责：
     * SecureWebViewFactory.release + destroy）；越界返回 null。
     *
     * AD-312（2026-10-02 审计）：挂起态按原标签透传——原实现恒 suspended=
     * false，后台标签崩溃重建后状态标记丢失（「真挂起」变「伪前台」，双
     * 活跃面回归）。需真挂起时对全新 WebView 立即 pause（替换件从未 pause
     * ——AD-060 的失真问题由真实 pause 消除，而非改标记）。显式传
     * [inheritSuspended]=false 恢复旧行为（前台标签崩溃重建直通）。
     */
    fun replaceWebView(
        index: Int,
        newWebView: WebView,
        inheritSuspended: Boolean = true,
    ): WebView? {
        if (index !in tabs.indices) return null
        val old = tabs[index].webView
        val targetSuspended = inheritSuspended && tabs[index].suspended
        if (targetSuspended) {
            pause(newWebView)
        }
        tabs[index] = tabs[index].copy(webView = newWebView, suspended = targetSuspended)
        return old
    }

    /**
     * AD-036（2026-09-24 审计）：页面 URL 回填的实例替换单写点。
     * 原 BrowserViewModel.onPageUrlObserved 经 `tab.url = url` 原地改 var——
     * list() 快照与 StateFlow 旧值持同一实例，data class self-equals 恒 true
     * → StateFlow 不发射。与 [updateTitle] 同模式（copy 替换实例）。
     * 越界/未知 id 静默忽略（对齐类内索引操作约定）。
     */
    fun updateUrl(
        id: Long,
        url: String,
    ) {
        val index = tabs.indexOfFirst { it.id == id }
        if (index >= 0) tabs[index] = tabs[index].copy(url = url)
    }

    /**
     * P0 修复2（真机复测 2026-09-02）：标题回填的实例替换单写点。
     * 原实现经 `tab.title = ...` 原地改 var——list() 快照与 StateFlow 旧值
     * 持有同一实例，data class self-equals 恒 true → StateFlow 不发射 →
     * UI 永不重组（chip 标题停在「新标签页」）。改用 copy 替换实例
     * （与 [replaceWebView] 同模式），StateFlow 依赖 equals 感知变化。
     * 越界静默忽略（对齐类内索引操作约定）。
     */
    fun updateTitle(
        id: Long,
        title: String,
    ) {
        val index = tabs.indexOfFirst { it.id == id }
        if (index >= 0) tabs[index] = tabs[index].copy(title = title)
    }

    /** 返回标签列表快照（防调用方改动内部结构）。 */
    fun list(): List<Tab> = tabs.toList()

    /** 全部挂起（调用点：MainActivity.onPause 后台化——AD-006 起的
     *  pauseTimers 全局停 JS 定时器+实例级挂起，隐私+电量缺口修复；
     *  回前台经 [resumeOnForeground] 对称恢复；onDestroy 销毁兜底不再
     *  走本函数——AD-072：suspendAll 只 pause，紧随的 tearDown 全量
     *  destroy 使 pause 全部冗余）。 */
    fun suspendAll() {
        // TabManager 补审（Android 官方）：挂起全部标签——onPause 实例级
        // + pauseTimers 全局暂停 JS timers（后台标签不继续跑 JS——资源/隐私）
        // P2 修复（全量复审 2026-09-01）：firstOrNull 防空列表崩溃
        // （原先 tabs.first() 在无标签时抛 NoSuchElementException）
        tabs.firstOrNull()?.webView?.pauseTimers()
        for ((i, tab) in tabs.withIndex()) {
            if (!tab.suspended) {
                pause(tab.webView)
                tabs[i] = tab.copy(suspended = true)
            }
        }
    }

    /** AD-006 回前台对称恢复：resumeTimers + 恢复当前标签；后台标签保持
     *  挂起，切换时由 [switchTo] 既有路径恢复。后台化由 [suspendAll]
     *  承担（onPause 生命周期复用，见该函数注记）。 */
    fun resumeOnForeground() {
        tabs.firstOrNull()?.webView?.resumeTimers()
        current()?.let { current ->
            if (current.suspended) {
                resume(current.webView)
                tabs[activeIndex] = current.copy(suspended = false)
            }
        }
    }

    // 2026-09-01 死代码清理（用户确认）：删除 findById / resumeCurrent。
    // 二者全工程 0 调用——suspendAll 仅在 onPause 后台化场景存在；
    // 未来若引入多标签挂起/恢复机制再按需重建。

    // ------------------------------------------------------------------ //
    // 私有：活跃上限策略
    // ------------------------------------------------------------------ //

    /** 当活跃（未挂起）标签数超过 maxActive 时，挂起最久未用的非活跃标签。

     LRU 策略（落地③：多标签性能优化，借鉴微软内存管理最佳实践）：
     优先挂起 lastUsed 最小的后台标签（而非按列表顺序），更贴近
     "最近最少使用"语义，减少用户近期将访问标签被挂起的概率。
     AD-079：时刻取 SystemClock.elapsedRealtime（单调时钟）——
     System.currentTimeMillis 是墙钟，用户改时间/NTP 回拨会打乱挂起次序。
     */
    private fun suspendOldestBeyondLimit() {
        val excess = tabs.count { !it.suspended } - maxActive
        if (excess <= 0) return
        // 按 lastUsed 升序（最久未用在前）取待挂起标签，排除当前标签
        val candidates =
            tabs
                .filter { !it.suspended && it.id != current()?.id }
                .sortedBy { it.lastUsed }
                .take(excess)
        for (tab in candidates) {
            pause(tab.webView)
            val index = tabs.indexOfFirst { it.id == tab.id }
            if (index >= 0) tabs[index] = tabs[index].copy(suspended = true)
        }
    }
}

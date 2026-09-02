package com.aegis.browser

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
 *
 * 本类不依赖任何 UI（Compose/Activity），可离线单测。
 */
class TabManager(
    private val maxActive: Int = 8,
    private val pause: (WebView) -> Unit = WebView::onPause,
    private val resume: (WebView) -> Unit = WebView::onResume,
) {
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
        title: String = "新标签页",
    ): Tab {
        val tab =
            Tab(
                id = nextId++,
                title = title,
                url = url,
                webView = webView,
                lastUsed = System.currentTimeMillis(),
            )
        tabs.add(tab)
        // 挂起旧标签，保证活跃标签数不超过上限（LRU：优先最久未用）
        suspendOldestBeyondLimit()
        switchTo(tabs.size - 1)
        return tab
    }

    /** 切换到指定标签并恢复其 WebView；越界返回 false。 */
    fun switchTo(index: Int): Boolean {
        if (index !in tabs.indices) return false
        // 挂起上一个激活标签（若不同且尚未挂起）
        val prev = current()
        if (prev != null && prev.id != tabs[index].id && !prev.suspended) {
            pause(prev.webView)
            prev.suspended = true
        }
        // 恢复目标标签并更新 LRU 时间戳（落地③：多标签性能优化）
        val target = tabs[index]
        if (target.suspended) {
            resume(target.webView)
            target.suspended = false
        }
        target.lastUsed = System.currentTimeMillis()
        activeIndex = index
        return true
    }

    /** 关闭指定标签，自动切换到相邻标签；越界或仅剩 1 个返回 false。 */
    fun closeTab(index: Int): Boolean {
        if (index !in tabs.indices) return false
        if (tabs.size <= 1) return false // 保留至少一个标签（浏览器约定）
        val removed = tabs.removeAt(index)
        pause(removed.webView) // 释放被关闭 WebView 的绘制资源
        // H-4 修复（审计 2026-08-31）：统一销毁序列（停载/摘除/注销/destroy 单源）
        SecureWebViewFactory.tearDown(removed.webView)
        activeIndex = if (index < tabs.size) index else tabs.size - 1
        current()?.let {
            if (it.suspended) {
                resume(it.webView)
                it.suspended = false
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
     */
    fun replaceWebView(
        index: Int,
        newWebView: WebView,
    ): WebView? {
        if (index !in tabs.indices) return null
        val old = tabs[index].webView
        tabs[index] = tabs[index].copy(webView = newWebView)
        return old
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

    /** 全部挂起（Activity 销毁兜底时调用——唯一调用点 MainActivity.onDestroy）。 */
    fun suspendAll() {
        // TabManager 补审（Android 官方）：挂起全部标签——onPause 实例级
        // + pauseTimers 全局暂停 JS timers（后台标签不继续跑 JS——资源/隐私）
        // P2 修复（全量复审 2026-09-01）：firstOrNull 防空列表崩溃
        // （原先 tabs.first() 在无标签时抛 NoSuchElementException）
        tabs.firstOrNull()?.webView?.pauseTimers()
        tabs.forEach {
            if (!it.suspended) {
                pause(it.webView)
                it.suspended = true
            }
        }
    }

    // 2026-09-01 死代码清理（用户确认）：删除 findById / resumeCurrent。
    // 二者全工程 0 调用——suspendAll 仅在 onDestroy 兜底场景存在，无恢复
    // 路径亦无需求（销毁即终止）；未来若引入多标签挂起/恢复机制再按需重建。

    // ------------------------------------------------------------------ //
    // 私有：活跃上限策略
    // ------------------------------------------------------------------ //

    /** 当活跃（未挂起）标签数超过 maxActive 时，挂起最久未用的非活跃标签。

     LRU 策略（落地③：多标签性能优化，借鉴微软内存管理最佳实践）：
     优先挂起 lastUsed 最小的后台标签（而非按列表顺序），更贴近
     "最近最少使用"语义，减少用户近期将访问标签被挂起的概率。
     */
    private fun suspendOldestBeyondLimit() {
        val active = tabs.filter { !it.suspended }
        val excess = active.size - maxActive
        if (excess <= 0) return
        // 按 lastUsed 升序（最久未用在前）取待挂起标签，排除当前标签
        val candidates =
            tabs
                .filter { !it.suspended && it.id != current()?.id }
                .sortedBy { it.lastUsed }
                .take(excess)
        for (tab in candidates) {
            pause(tab.webView)
            tab.suspended = true
        }
    }
}

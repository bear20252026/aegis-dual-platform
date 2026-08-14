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
    fun addTab(webView: WebView, url: String = "", title: String = "新标签页"): Tab {
        val tab = Tab(id = nextId++, title = title, url = url, webView = webView,
            lastUsed = System.currentTimeMillis())
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
        removed.webView.destroy()
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

    /** 返回标签列表快照（防调用方改动内部结构）。 */
    fun list(): List<Tab> = tabs.toList()

    /** 按 id 查找标签；不存在返回 null。 */
    fun findById(id: Long): Tab? = tabs.firstOrNull { it.id == id }

    /** 全部挂起（窗口不可见 / Activity 暂停时调用）。 */
    fun suspendAll() {
        tabs.forEach {
            if (!it.suspended) {
                pause(it.webView)
                it.suspended = true
            }
        }
    }

    /** 仅恢复当前标签（窗口重新可见时调用）。 */
    fun resumeCurrent() {
        current()?.let {
            if (it.suspended) {
                resume(it.webView)
                it.suspended = false
            }
        }
    }

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
        val candidates = tabs
            .filter { !it.suspended && it.id != current()?.id }
            .sortedBy { it.lastUsed }
            .take(excess)
        for (tab in candidates) {
            pause(tab.webView)
            tab.suspended = true
        }
    }
}

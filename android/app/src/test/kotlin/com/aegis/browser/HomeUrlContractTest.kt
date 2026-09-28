package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * AD-124（审计 2026-09-23 清单·A6 批）：HOME_URL 单源契约守护测试——首页
 * URL 字面量只允许出现在 BrowserEngine（assets 单源约定，ADR-007）；
 * BrowserViewModel.HOME_URL 必须委托同一常量，首页占位展示常量随之锁定。
 * 任一端改动首页路径而未同步另一端时在此失败。
 */
class HomeUrlContractTest {
    @Test
    fun homeUrlLiteralIsLockedToAssetsShellPage() {
        assertEquals("file:///android_asset/start.html", BrowserEngine.HOME_URL)
    }

    @Test
    fun viewModelHomeUrlDelegatesToEngineSingleSource() {
        assertEquals(BrowserEngine.HOME_URL, BrowserViewModel.HOME_URL)
    }

    @Test
    fun homeDisplayPlaceholderStaysNonNavigable() {
        // AD-063：地址栏首页占位——不可被策略放行的伪 scheme（防用户提交占位）
        assertEquals("aegis://home", BrowserViewModel.HOME_DISPLAY_URL)
    }
}

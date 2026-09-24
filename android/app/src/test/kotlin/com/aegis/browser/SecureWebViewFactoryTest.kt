package com.aegis.browser

import android.webkit.WebView
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import org.mockito.Mockito.mock

/**
 * SecureWebViewFactory 导航器注册表 JVM 单测（2026-09-24 审计——AD-022）。
 * create() 依赖 Android 框架（WebView/Context）不在 JVM 覆盖范围——
 * 本测试锁定注册表查询/释放的 fail-closed 边界。
 */
class SecureWebViewFactoryTest {
    @Test
    fun navigatorForUnregisteredWebViewReturnsNull() {
        val stranger = mock(WebView::class.java)
        // 仅工厂 create() 的 WebView 才有导航器——未知实例必须 null（调用方拒绝外部导航）
        assertNull(SecureWebViewFactory.navigatorFor(stranger))
    }

    @Test
    fun releaseOfUnregisteredWebViewIsNoOp() {
        val stranger = mock(WebView::class.java)
        SecureWebViewFactory.release(stranger)
        SecureWebViewFactory.tearDown(stranger)
        assertNull(SecureWebViewFactory.navigatorFor(stranger))
    }

    @Test
    fun distinctUnregisteredWebViewsEachReturnNull() {
        // 注册表按实例键——不同 mock 实例互不相通，均为未注册
        val a = mock(WebView::class.java)
        val b = mock(WebView::class.java)
        assertFalse(a === b)
        assertNull(SecureWebViewFactory.navigatorFor(a))
        assertNull(SecureWebViewFactory.navigatorFor(b))
    }
}

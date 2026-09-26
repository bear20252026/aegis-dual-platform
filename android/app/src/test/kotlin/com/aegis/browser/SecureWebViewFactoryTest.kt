package com.aegis.browser

import android.webkit.WebView
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import org.mockito.Mockito.inOrder
import org.mockito.Mockito.mock
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when` as whenever

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

    // ---------------- AD-214（2026-09-26 审计）：attached destroy 泄漏回归 ----------------

    @Test
    fun tearDownDetachesWebViewFromParentBeforeDestroy() {
        // destroy 前必须先从父容器摘除——仍挂在视图树上的 destroy 是
        // Chromium 资源泄漏（官方生命周期要求；mockito 5 inline 可 stub
        // View.getParent）
        val wv = mock(WebView::class.java)
        val parent = mock(android.view.ViewGroup::class.java)
        whenever(wv.parent).thenReturn(parent)
        SecureWebViewFactory.tearDown(wv)
        val order = inOrder(parent, wv)
        order.verify(parent).removeView(wv)
        order.verify(wv).destroy()
    }

    @Test
    fun tearDownWithoutParentStillDestroys() {
        // 无父容器（未挂载/已摘除）路径不受 detach 步骤影响
        val wv = mock(WebView::class.java)
        SecureWebViewFactory.tearDown(wv)
        verify(wv).destroy()
    }
}

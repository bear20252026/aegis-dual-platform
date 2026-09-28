package com.aegis.browser

import android.content.Context
import android.content.pm.PackageInfo
import androidx.test.core.app.ApplicationProvider
import androidx.webkit.WebViewCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.ArgumentMatchers.any
import org.mockito.MockedStatic
import org.mockito.Mockito
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * AD-115（审计 2026-09-23 清单·A6 批）：getWebViewVersion 异常/缺 provider
 * 路径单测——provider 查询抛异常必须折叠为 null（不阻塞浏览）、null package
 * 折叠为 null、正常 package 映射（name/longVersionCode）、checkAndPrompt 在
 * 异常路径零回调不崩溃。WebViewCompat.getCurrentWebViewPackage 为静态调用，
 * 经 mockito mockStatic 注入（Robolectric 提供真实资源 getString）。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WebViewVersionCheckProviderTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    private fun stubCurrentPackage(stub: () -> PackageInfo?): MockedStatic<WebViewCompat> =
        Mockito
            .mockStatic(WebViewCompat::class.java)
            .also { mocked ->
                mocked.`when`<PackageInfo?> { WebViewCompat.getCurrentWebViewPackage(any()) }.thenAnswer { stub() }
            }

    @Test
    fun providerQueryExceptionFoldsToNull() {
        stubCurrentPackage { throw IllegalStateException("provider binder crash") }.use {
            assertNull("查询异常必须折叠为 null（不阻塞浏览）", WebViewVersionCheck.getWebViewVersion(context))
        }
    }

    @Test
    fun nullCurrentPackageFoldsToNull() {
        stubCurrentPackage { null }.use {
            assertNull(WebViewVersionCheck.getWebViewVersion(context))
        }
    }

    @Test
    fun currentPackageMapsNameAndLongVersionCode() {
        val pkg = PackageInfo()
        pkg.versionName = "141.0.7390.0"
        pkg.longVersionCode = 141_000_7390L
        stubCurrentPackage { pkg }.use {
            val version = WebViewVersionCheck.getWebViewVersion(context)
            assertNotNull(version)
            assertEquals("141.0.7390.0", version!!.name)
            assertEquals(141_000_7390L, version.code)
        }
    }

    @Test
    fun checkAndPromptSwallowsProviderExceptionWithoutCallback() {
        var called = false
        stubCurrentPackage { throw IllegalStateException("provider binder crash") }.use {
            WebViewVersionCheck.checkAndPrompt(context) { called = true }
            assertFalse("异常路径不得触发提示回调", called)
        }
    }

    @Test
    fun checkAndPromptSurfacesOutdatedVersionMessage() {
        val pkg = PackageInfo()
        pkg.versionName = "80.0.1"
        pkg.longVersionCode = 1_000L
        var message: String? = null
        stubCurrentPackage { pkg }.use {
            WebViewVersionCheck.checkAndPrompt(context) { message = it }
            assertNotNull("过旧版本必须触发提示", message)
            assertTrue("提示须携带实际版本号", message!!.contains("80.0.1"))
        }
    }

    @Test
    fun checkAndPromptStaysSilentForCurrentVersion() {
        val pkg = PackageInfo()
        pkg.versionName = "141.0.7390.0"
        pkg.longVersionCode = 141_000_7390L
        var message: String? = null
        stubCurrentPackage { pkg }.use {
            WebViewVersionCheck.checkAndPrompt(context) { message = it }
            assertNull(message)
        }
    }
}

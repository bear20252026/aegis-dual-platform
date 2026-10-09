package com.aegis.browser

import com.aegis.broker.ReservedAddressBoundary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 下载目标形态闸门的 JVM 用例（R8-AD-03，第八轮 2026-10-08）。
 *
 * 这里测的是 `rejectionOf`——纯判定面，零 Android 类型 ⇒ 不需要 Robolectric。
 * 段表本身（哪些地址算保留）由 `:broker` 的 ReservedAddressBoundaryTest 逐段钉，
 * 本文件钉的是**下载侧接线**：命中形态拿到的是哪条文案、留痕里有没有跨端统一
 * 拒绝码、以及 B8 裁决要求能下载的本机/内网目标有没有被顺手拦掉。
 * 拒绝组与放行组必须同时存在——只留拒绝组，这条闸门可以在「全拒」下悄悄全绿。
 */
class WebViewDownloadTargetGuardTest {
    @Test
    fun reservedTargetsGetTheReservedMessageAndCode() {
        val urls =
            listOf(
                "http://169.254.169.254/latest/user-data",
                "http://169.254.1.1/open/",
                "http://0.0.0.0/x",
                "http://239.255.255.250/ssdp",
                "http://[fe80::1]/",
                "http://2852168190/",
            )
        for (url in urls) {
            val rejection = WebViewDownloadTargetGuard.rejectionOf(url, "http")
            assertNotNull("保留地址下载必须被拦: $url", rejection)
            assertTrue(
                "留痕必须带跨端统一拒绝码: $url",
                rejection!!.first.contains("code=${ReservedAddressBoundary.DENY_CODE}"),
            )
            assertEquals(R.string.download_blocked_reserved, rejection.second)
        }
    }

    @Test
    fun unsupportedSchemeKeepsItsOwnMessage() {
        val rejection =
            requireNotNull(WebViewDownloadTargetGuard.rejectionOf("blob:https://cdn/x", "blob")) {
                "非 http(s) 必须被拦"
            }
        assertEquals(R.string.download_blocked_type, rejection.second)
        assertTrue(rejection.first.contains("blob"))
    }

    @Test
    fun schemeJudgeRunsBeforeTheAddressJudge() {
        // 顺序锚点：scheme 不支持时不该说成「保留地址」——用户看到的理由必须是真的那个。
        val rejection =
            requireNotNull(WebViewDownloadTargetGuard.rejectionOf("http://169.254.169.254/x", "ftp"))
        assertEquals(R.string.download_blocked_type, rejection.second)
    }

    @Test
    fun loopbackPrivateCgnatAndPublicTargetsStayDownloadable() {
        // 第七轮 B8「本机与内网必须能打开」在下载层的下界；收紧即本用例红。
        val allowed =
            listOf(
                "http://127.0.0.1:8000/a.zip" to "http",
                "http://10.0.0.5/share.bin" to "http",
                "http://192.168.1.1:8080/fw.bin" to "http",
                "http://100.64.1.2/x" to "http",
                "http://my-nas.local/share.bin" to "http",
                "https://example.com/app.apk" to "https",
            )
        for ((url, scheme) in allowed) {
            assertNull("本机/内网/公网目标不得被这条闸门拦: $url", WebViewDownloadTargetGuard.rejectionOf(url, scheme))
        }
    }
}

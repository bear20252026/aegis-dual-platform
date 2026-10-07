package com.aegis.browser

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⑦（第八轮，用户 2026-10-07 定稿）：canvas **像素直读出口**的注入文本结构锚。
 *
 * 被消除的形态：噪声只加在编码三出口（`toDataURL`/`toBlob`/`convertToBlob`）上，
 * 而 `ctx.getImageData(...)` 与 `gl.readPixels(...)` 直读到无噪原文——页面把两条
 * 出口逐像素比对，差异本身就是「防护存在」的一行判据（R8-RS-03）。
 *
 * 这里钉的是 Android 端最容易写坏的两件事：
 * ① 子矩形读回必须换算成**画布绝对像素序号**，否则同一点在两条出口拿到不同扰动；
 * ② 编码路径必须用**未包裹**的 `getImageData`——离屏副本若再走一次加噪，
 * 两条出口就不再相同（本项要消除的东西被换个位置再造一遍）。
 * 跨端同形由 `core/rust-policy-core/tests/canvas_read_channels.rs` 对账三份源码。
 */
class WebViewHardeningCanvasReadTest {
    private val script =
        WebViewHardening.fingerprintShieldScript(
            "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
        )

    @Test
    fun pixelReadbackChannelsAreNoised() {
        assertTrue(
            "缺单源矩形噪声函数",
            script.contains("function aegisNoiseRectangle(data, seed, sx, sy, sw, sh, stride)"),
        )
        assertTrue("getImageData 未被包裹", script.contains("owner.getImageData = function(sx, sy, sw, sh)"))
        assertTrue(
            "readPixels 未被包裹",
            script.contains("owner.readPixels = function(x, y, width, height, format, type, pixels)"),
        )
        assertTrue("子矩形必须换算成绝对像素序号", script.contains("(sy + row) * stride + (sx + col)"))
    }

    @Test
    fun encodingPathReadsThroughTheUnwrappedOriginal() {
        assertFalse(
            "编码路径不得调用已包裹的 getImageData（副本会被加噪两次）",
            script.contains("octx.getImageData(0, 0, off.width, off.height)"),
        )
        assertTrue(
            "编码路径必须用未包裹原实现",
            script.contains("AEGIS_RAW_GET_IMAGE_DATA.call(octx, 0, 0, off.width, off.height)"),
        )
        assertTrue(
            "worker 副本用 OffscreenCanvas 自己的未包裹原实现",
            script.contains("AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA || AEGIS_RAW_GET_IMAGE_DATA"),
        )
    }

    @Test
    fun alphaUntouchedAndWebglGuardBounded() {
        assertFalse("alpha 通道不得被扰动（透明度变化视觉可察）", script.contains("data[i + 3]"))
        assertTrue("WebGL 只加噪 8 位 RGBA 缓冲", script.contains("pixels.length === width * height * 4"))
    }
}

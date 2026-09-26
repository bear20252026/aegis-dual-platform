package com.aegis.browser

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * AD-248（2026-09-26 审计）：uriEncode 与 android.net.Uri.encode(text, "/")
 * 的完整对照矩阵（instrumented——Uri.encode 是平台实现，JVM android.jar 为
 * stub 无法断言）。SearchEngines.uriEncode 声称与其语义一致（AD-057），
 * 此前仅 2 条冒烟；keep 集漂移（如 `!`，AOSP isAllowed 放行集
 * "_-!.~'()*"）在此逐字节暴露。
 */
@RunWith(AndroidJUnit4::class)
class SearchEnginesUriEncodeInstrumentedTest {
    private val matrix =
        listOf(
            "",
            "helloworld",
            "a/b",
            "a.b-c_d~e'f(g)h*i!j",
            "hello world",
            "100%",
            "rust + uniffi",
            "中文",
            "？#&=", // 全角问号 + 保留字符
            "line1\nline2",
            "tab\tchar",
            "quote\"double'single",
            "<>&",
            "\\backslash",
            "emoji😀bytes",
            "  leading and trailing  ",
            "mikey's~site!(v2)*-._/",
            "café中文mix",
            "{secret}|^`",
        )

    @Test
    fun uriEncodeMatchesPlatformUriEncodeWithSlashAllow() {
        for (input in matrix) {
            assertEquals(
                "uriEncode 与 Uri.encode(input, \"/\") 必须逐字节一致: <$input>",
                Uri.encode(input, "/"),
                SearchEngines.uriEncode(input),
            )
        }
    }
}

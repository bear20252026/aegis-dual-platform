package com.aegis.browser

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * AegisHomeBridge.getEngine JSON 消费契约 JVM 单测（2026-09-26 审计——AD-250）。
 * @JavascriptInterface 方法必须 public（JS 反射仅暴露 public 注解方法，无法
 * 直接 internal 化）——buildEngineJson 抽取纯函数锁定与 start.html 的
 * 契约：`{"engine":<key>,"engines":[{"key","name"}]}`。桥实例完整链路
 * （受信壳页校验/SharedPreferences）依赖 Android 框架，由真机走查覆盖。
 */
class AegisHomeBridgeTest {
    @Test
    fun engineJsonMatchesStartHtmlContract() {
        val payload = JSONObject(AegisHomeBridge.buildEngineJson("baidu"))
        assertEquals("baidu", payload.getString("engine"))
        val engines = payload.getJSONArray("engines")
        assertEquals(
            "引擎清单必须与 SearchEngines.ENGINE_URLS 一致",
            SearchEngines.ENGINE_URLS.size,
            engines.length(),
        )
        val keys = mutableSetOf<String>()
        for (i in 0 until engines.length()) {
            val entry = engines.getJSONObject(i)
            keys.add(entry.getString("key"))
            assertTrue("每个引擎条目必须含显示名", entry.getString("name").isNotBlank())
        }
        assertEquals(SearchEngines.ENGINE_URLS.keys, keys)
    }

    @Test
    fun engineJsonCarriesRequestedCurrentEngine() {
        // current 透传非默认值（getEngine 读偏好后传入——结构不得锁死默认引擎）
        val payload = JSONObject(AegisHomeBridge.buildEngineJson("sogou"))
        assertEquals("sogou", payload.getString("engine"))
    }
}

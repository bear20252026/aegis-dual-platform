package com.aegis.browser

import android.webkit.WebView
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature

/**
 * WebView 硬化脚本注入（单文件单职责：从 SecureWebViewFactory 拆出）。
 *
 * 包含两类 document-start 注入：
 * 1. bridge-guard：Bridge 硬化 JS（fetch/XHR/sendBeacon/WebSocket 未授权调用拒绝）
 *    ——单一事实源（ADR-007）：模板与 `contracts/schemas/bridge_guard.template.js`
 *    逐行一致，由 `contracts/codegen/verify_bridge_guard.py` 门禁校验。
 * 2. fingerprint-shield：9 阶段指纹防护 JS（canvas/WebGL/Audio 噪声 +
 *    hardwareConcurrency 伪装），每会话随机种子确定性——同一会话内指纹
 *    一致但跨会话不同。canvas 噪声自 AD-212（2026-09-26 审计）起施加在
 *    离屏副本（与 Rust 侧 RS-025 修复模式对齐）。
 */
internal object WebViewHardening {
    /** 会话随机种子字节数（hex 输出——注入 JS 噪声用）。 */
    private const val SESSION_SEED_BYTES = 32

    /** 每会话随机种子（32 字节 hex）——注入 JS 噪声时用。 */
    fun newSessionSeed(): String {
        val bytes = ByteArray(SESSION_SEED_BYTES)
        java.security.SecureRandom().nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    /** 在每个主文档创建前注入策略脚本；不支持时显式降级，不伪称已受保护。 */
    fun install(
        webView: WebView,
        sessionSeed: String,
    ) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            android.util.Log.w("Aegis", "WebView 不支持 document-start 脚本；隐私增强未启用")
            return
        }
        // allowedOriginRules 语法：AndroidX 不接受 "https://*" 全域通配
        // （IllegalArgumentException）——单星号 "*" 才是「匹配所有源
        // （含 file:// 壳页）」的合法写法，与防护脚本全页注入的意图一致。
        // 降级原则：注入失败（WebView provider 异常等）只警告不崩——
        // 防护可降级、浏览器不可崩（配套 proguard keep androidx.webkit.R$id）。
        val allowedOrigins = setOf("*")
        val hardenedScripts =
            listOf(
                "fingerprint-shield" to fingerprintShieldScript(sessionSeed),
                "bridge-guard" to BRIDGE_GUARD_JS,
            )
        hardenedScripts.forEach { (name, script) ->
            try {
                WebViewCompat.addDocumentStartJavaScript(webView, script, allowedOrigins)
            } catch (e: Exception) {
                android.util.Log.e("Aegis", "document-start 注入失败[$name]: ${e.message}")
            }
        }
    }

    /** 允许的 bridge 域名白名单（编译期固定单源——经占位符注入 bridge_guard
     *  模板，与 Rust BridgeGuard 白名单同源；AD-076：原注「可动态扩展」与
     *  实现不符——本表无任何运行期写入路径）。 */
    private val ALLOWED_BRIDGE_HOSTS =
        listOf(
            "aegis.local",
            "localhost",
            "127.0.0.1",
        )

    /** bridge 域名白名单 JSON（ktlint 可解析——避免嵌套 \${} 复杂表达式）。 */
    private val allowedHostsJson: String =
        ALLOWED_BRIDGE_HOSTS.joinToString(",") { "\"$it\"" }

    /** REQUIRE_HTTPS 占位符注入值（模板归一化为 __AEGIS_REQUIRE_HTTPS__）。 */
    private val requireHttpsJson: String = REQUIRE_HTTPS_BRIDGE.toString()

    /**
     * bridge 目标强制 HTTPS（与 Rust BridgeGuard.require_https 对应）。
     * 生产接线已开启（2026-09-10，两端一致）：受信内页对 bridge 目标
     * （aegis.local/localhost/127.0.0.1）的 http: 调用一律拒绝——bridge 面
     * 无明文需求（首页数据全走 AegisBridge 注入对象而非 HTTP bridge）。
     * Rust 侧 BridgeGuard::new 无生产调用点（库能力 + 双值测试覆盖），
     * 模板一致性由 verify_bridge_guard.py 门禁保证。
     */
    private const val REQUIRE_HTTPS_BRIDGE = true

    /**
     * Bridge 硬化 JS（fetch / XMLHttpRequest / sendBeacon / WebSocket 未授权调用拒绝）。
     *
     * 单一事实源（ADR-007）：本模板必须与
     * `contracts/schemas/bridge_guard.template.js` 逐行一致（占位符归一化后），
     * 由 `contracts/codegen/verify_bridge_guard.py` 门禁校验——禁止手工改动
     * 本模板而不更新规范文件（fail-open 漂移即此模式的产物）。
     *
     * AD-069（2026-09-24 审计）：private → internal——JVM 单测断言关键防御
     * 标记存在（fetch/XHR/beacon/WS 劫持点、白名单、REQUIRE_HTTPS），杜绝
     * 「脚本内容被改而注入照常」的零回归盲区。
     */
    internal val BRIDGE_GUARD_JS: String
        get() =
            """
// Aegis BridgeGuard — 受信调用方校验（fetch / XMLHttpRequest / sendBeacon / WebSocket）
// REQUIRED_SINKS: window.fetch = function|XMLHttpRequest.prototype.open|navigator.sendBeacon = function|window.WebSocket = function|trustedCaller|location.hostname
// ↑ PY-043 单源：verify_bridge_guard.py 的 REQUIRED_SINKS 自此行解析
//   （此前 Python 手工副本——Rust include_str! 编译期消费本文件，清单随模板演进自动同步）
(function() {
  const ALLOWED_HOSTS = [$allowedHostsJson];
  const REQUIRE_HTTPS = $requireHttpsJson;
  // 仅容许「受信内页」（自身 hostname ∈ 白名单）调用本机 bridge。
  const trustedCaller = ALLOWED_HOSTS.includes(location.hostname);
  function isBridgeTarget(urlLike) {
    try { return ALLOWED_HOSTS.includes(new URL(urlLike, location.href).hostname); }
    catch (e) { return false; }
  }
  function shouldBlock(urlLike) {
    if (!isBridgeTarget(urlLike)) return false;   // 普通站点流量放行
    if (!trustedCaller) return true;              // 调用方非受信内页 → 拒绝
    if (REQUIRE_HTTPS) {
      try { if (new URL(urlLike, location.href).protocol !== 'https:') return true; } catch (e) {}
    }
    return false;
  }
  function deny(reason) { console.warn('[Aegis] Bridge blocked: ' + reason); }
  // RS-242（2026-10-01 审计）：四桥出口注册 ToStringGuard（proxy.register.v1，
  // 与 shield.rs 同款）——未注册时 fetch.toString() 一行暴露包装源码
  //（内含品牌特征）。注册接口缺失/参数非法时为空转（防御性 if 守卫）
  var __aegisReg = window[Symbol.for('proxy.register.v1')];
  const fetch0 = window.fetch;
  window.fetch = function(input, init) {
    if (shouldBlock(input && input.url ? input.url : input)) { deny('fetch'); return Promise.reject(new Error('Aegis: bridge blocked')); }
    return fetch0.apply(this, arguments);
  };
  if (__aegisReg) __aegisReg(window.fetch, fetch0);
  const open0 = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (shouldBlock(url)) { deny('xhr'); throw new Error('Aegis: bridge blocked'); }
    return open0.apply(this, arguments);
  };
  if (__aegisReg) __aegisReg(XMLHttpRequest.prototype.open, open0);
  // PY-249（2026-10-01 审计）：beacon0 缺 .bind(navigator) 笔误——
  // `sendBeacon && sendBeacon` 恒等自身，调用时 this 丢失（严格模式 TypeError
  // 守卫自炸）。保留存在性短路 + 明确 bind
  const beacon0 = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);
  navigator.sendBeacon = function(url) {
    if (shouldBlock(url)) { deny('beacon'); return false; }
    return beacon0.apply(navigator, arguments);
  };
  if (__aegisReg && beacon0) __aegisReg(navigator.sendBeacon, beacon0);
  const WS = window.WebSocket;
  window.WebSocket = function(url, protocols) {
    if (shouldBlock(url)) { deny('websocket'); throw new Error('Aegis: bridge blocked'); }
    return new WS(url, protocols);
  };
  window.WebSocket.CONNECTING = WS.CONNECTING;
  window.WebSocket.OPEN = WS.OPEN;
  window.WebSocket.CLOSING = WS.CLOSING;
  window.WebSocket.CLOSED = WS.CLOSED;
  // AD-105（审计 2026-09-23 清单·A6 批）：原型链对齐——包装函数默认
  // prototype 与真 WebSocket 实例无关，new WebSocket(...) instanceof
  // WebSocket 恒 false（页面一行即可探测防护存在性）。
  window.WebSocket.prototype = WS.prototype;
  if (__aegisReg) __aegisReg(window.WebSocket, WS);
})();
            """.trimIndent()

    /**
     * 指纹防护 JS（管道化组合——参照 Rust fingerprint_pipeline）。
     *
     * AD-247（2026-09-26 审计）：private → internal——9 阶段脚本此前无任何 JVM 断言，
     * 「脚本被改而注入照常」是零回归盲区（BRIDGE_GUARD_JS 已有 AD-069 同口径标记回归，
     * 本脚本对齐补齐）。R8-SH-15/16、R8-RS-04/09 的常驻断言都挂在这个入口上。
     *
     * R8-CS-SEC-14（第八轮）：文本按 Stage 边界外迁到 WebViewHardeningStagesSeed /
     * ...Shield 两个文件，这里只保留**注入入口与顺序**——顺序是安全语义的一部分。
     */
    internal fun fingerprintShieldScript(sessionSeed: String): String =
        WebViewHardeningStagesSeed.script(sessionSeed) + "\n" + WebViewHardeningStagesShield.script()
}

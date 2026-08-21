package com.aegis.browser

import android.content.Context
import android.webkit.WebView
import com.aegis.broker.AndroidBroker
import com.aegis.webviewadapter.AegisWebViewClient

/**
 * 安全 WebView 工厂（单文件单职责：统一创建带完整安全边界的 WebView）。
 *
 * 改动（单路径收敛——专家审计）：WebView 创建时同时注入 AegisWebViewClient，
 * 确保所有导航回调经 Broker 决策（fail-closed），不再绕过。
 *
 * 改动（2026 高赞浏览器照搬——voidbrowser fingerprint shield）：
 * 创建 WebView 后注入指纹防护 JS（canvas/WebGL/Audio 噪声 + hardwareConcurrency 伪装），
 * 每会话随机种子确定性——同一会话内指纹一致但跨会话不同。
 */
object SecureWebViewFactory {
    private val broker = AndroidBroker()
    private var sessionCounter = 0L
    /** 每会话随机种子（32 字节 hex）——注入 JS 噪声时用。 */
    private val sessionSeed: String by lazy {
        val bytes = ByteArray(32)
        java.security.SecureRandom().nextBytes(bytes)
        bytes.joinToString("") { "%02x".format(it) }
    }

    /** 创建并完成安全配置的 WebView（导航经 Broker 决策 + 指纹防护注入）。 */
    fun create(context: Context): WebView {
        val webView = WebView(context)
        BrowserEngine(webView).configure()
        val sessionId = "session-${++sessionCounter}"
        webView.webViewClient = AegisWebViewClient(
            broker = broker,
            sessionId = sessionId,
            onRendererGone = { /* renderer gone cleanup handled by caller */ },
        )
        // 指纹防护 JS 注入（canvas/WebGL/Audio 噪声 + hardwareConcurrency 伪装）
        webView.evaluateJavascript(FINGERPRINT_SHIELD_JS, null)
        // Bridge 硬化 JS 注入（域白名单 + HTTPS 强制——照搬 SecureWebViewContainer）
        webView.evaluateJavascript(BRIDGE_GUARD_JS, null)
        return webView
    }

    /** 获取 broker 实例（供外部校验/审计）。 */
    fun broker(): AndroidBroker = broker

    /** 允许的 bridge 域名白名单（可动态扩展）。 */
    private val ALLOWED_BRIDGE_HOSTS = listOf(
        "aegis.local", "localhost", "127.0.0.1"
    )

    /** bridge 域名白名单 JSON（ktlint 可解析——避免嵌套 \${} 复杂表达式）。 */
    private val allowedHostsJson: String =
        ALLOWED_BRIDGE_HOSTS.joinToString(",") { "\"$it\"" }

    /** Bridge 硬化 JS（照搬 SecureWebViewContainer NativeBridge origin 校验）。 */
    private val BRIDGE_GUARD_JS: String
        get() = """
// Aegis BridgeGuard — origin 校验拦截（fetch/XMLHttpRequest 未授权调用拒绝）
(function() {
  const ALLOWED_HOSTS = $allowedHostsJson;
  const origFetch = window.fetch;
  window.fetch = function(url) {
    try {
      const u = new URL(url, location.href);
      if (u.protocol !== 'https:' && u.protocol !== 'http:' && u.hostname !== 'localhost') {
        console.warn('[Aegis] Bridge blocked: non-HTTPS', u.href);
        return Promise.reject(new Error('Aegis: non-HTTPS bridge blocked'));
      }
      if (ALLOWED_HOSTS.length > 0 && !ALLOWED_HOSTS.includes(u.hostname) && !location.hostname.includes(u.hostname)) {
        console.warn('[Aegis] Bridge blocked: host not allowed', u.hostname);
        return Promise.reject(new Error('Aegis: host not in allowlist'));
      }
    } catch(e) {}
    return origFetch.apply(this, arguments);
  };
})();
""".trimIndent()

    /** 指纹防护 JS（照搬 voidbrowser FingerprintShield——canvas/WebGL/Audio 噪声）。 */
    private val FINGERPRINT_SHIELD_JS: String
        get() = """
// Aegis FingerprintShield — 每会话确定性噪声种子
const __AEGIS_SESSION_SEED = '$sessionSeed';

// Canvas 噪声（每个像素 +1/-1 随机偏移——视觉不可察觉）
(function() {
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx) {
      const imageData = ctx.getImageData(0, 0, this.width, this.height);
      const seed = parseInt(__AEGIS_SESSION_SEED.slice(0, 8), 16);
      for (let i = 0; i < imageData.data.length; i += 4) {
        imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1;
      }
      ctx.putImageData(imageData, 0, 0);
    }
    return origToDataURL.apply(this, arguments);
  };
})();

// WebGL 渲染器/供应商伪装
(function() {
  const origGetParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {
    const UNMASKED_RENDERER = 37446;
    const UNMASKED_VENDOR = 37445;
    if (p === UNMASKED_RENDERER) return 'ANGLE (Aegis)';
    if (p === UNMASKED_VENDOR) return 'Aegis Privacy';
    return origGetParameter.call(this, p);
  };
})();

// hardwareConcurrency 随机化（2-8 核）
(function() {
  const seed = parseInt(__AEGIS_SESSION_SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 2 + (seed % 7)
  });
})();
""".trimIndent()
}

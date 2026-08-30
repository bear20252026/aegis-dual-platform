package com.aegis.browser

import android.content.Context
import android.view.View
import android.webkit.WebView
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.aegis.broker.AndroidBroker
import com.aegis.broker.ApprovalRequest
import com.aegis.webviewadapter.AegisWebViewClient
import java.util.concurrent.atomic.AtomicLong

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
    private val sessionCounter = AtomicLong(0)
    private val navigatorTagKey = View.generateViewId()

    /** 会话随机种子字节数（hex 输出——注入 JS 噪声用）。 */
    private const val SESSION_SEED_BYTES = 32

    /** 每会话随机种子（32 字节 hex）——注入 JS 噪声时用。 */
    private fun newSessionSeed(): String {
        val bytes = ByteArray(SESSION_SEED_BYTES)
        java.security.SecureRandom().nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    /** 创建并完成安全配置的 WebView（导航经 Broker 决策 + 指纹防护注入）。 */
    fun create(
        context: Context,
        onNavigationConfirmationRequested: (WebView, ApprovalRequest) -> Unit = { _, _ -> },
        onNavigationConfirmationResolved: (WebView) -> Unit = {},
    ): WebView {
        val webView = WebView(context)
        BrowserEngine(webView).configure()
        val sessionId = "session-${sessionCounter.incrementAndGet()}"
        val tabId = "tab-$sessionId"
        if (!broker.registerSession(sessionId, tabId)) {
            // fail-closed 前留根因线索（logcat -s AegisBroker；典型：
            // release minified 混淆 JNA Abi 接口 → native 符号映射失败）
            android.util.Log.e(
                "AegisBroker",
                "registerSession failed: session=$sessionId, " +
                    "REQUIRE_NATIVE_POLICY_CORE=${com.aegis.broker.BuildConfig.REQUIRE_NATIVE_POLICY_CORE}",
            )
            check(false) { "无法注册安全浏览会话（详见 logcat -s AegisBroker）" }
        }
        val sessionSeed = newSessionSeed()
        installDocumentStartScripts(webView, sessionSeed)
        val client =
            AegisWebViewClient(
                broker = broker,
                sessionId = sessionId,
                tabId = tabId,
                onRendererGone = { /* renderer gone cleanup handled by caller */ },
                requireNavigationConfirmation = BuildConfig.REQUIRE_NAVIGATION_CONFIRMATION,
                onNavigationConfirmationRequested = { request ->
                    onNavigationConfirmationRequested(webView, request)
                },
                onNavigationConfirmationResolved = { onNavigationConfirmationResolved(webView) },
            )
        webView.webViewClient = client
        webView.setTag(
            navigatorTagKey,
            SecureNavigator(webView, client),
        )
        return webView
    }

    /** 仅工厂创建的 WebView 才拥有受控导航器；不存在时调用方必须拒绝外部导航。 */
    fun navigatorFor(webView: WebView): SecureNavigator? = webView.getTag(navigatorTagKey) as? SecureNavigator

    /** 在每个主文档创建前注入策略脚本；不支持时显式降级，不伪称已受保护。 */
    private fun installDocumentStartScripts(
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
            listOf("fingerprint-shield" to fingerprintShieldScript(sessionSeed),
                "bridge-guard" to BRIDGE_GUARD_JS)
        hardenedScripts.forEach { (name, script) ->
            try {
                WebViewCompat.addDocumentStartJavaScript(webView, script, allowedOrigins)
            } catch (e: Exception) {
                android.util.Log.e("Aegis", "document-start 注入失败[$name]: ${e.message}")
            }
        }
    }

    /** 获取 broker 实例（供外部校验/审计）。 */
    fun broker(): AndroidBroker = broker

    /** 允许的 bridge 域名白名单（可动态扩展）。 */
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
     * 生产接线尚未开启（两端一致）；配置化时须同步 BridgeGuard::new 调用点。
     */
    private const val REQUIRE_HTTPS_BRIDGE = false

    /**
     * Bridge 硬化 JS（fetch / XMLHttpRequest / sendBeacon / WebSocket 未授权调用拒绝）。
     *
     * 单一事实源（ADR-007）：本模板必须与
     * `contracts/schemas/bridge_guard.template.js` 逐行一致（占位符归一化后），
     * 由 `contracts/codegen/verify_bridge_guard.py` 门禁校验——禁止手工改动
     * 本模板而不更新规范文件（fail-open 漂移即此模式的产物）。
     */
    private val BRIDGE_GUARD_JS: String
        get() =
            """
// Aegis BridgeGuard — 受信调用方校验（fetch / XMLHttpRequest / sendBeacon / WebSocket）
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
  const fetch0 = window.fetch;
  window.fetch = function(input, init) {
    if (shouldBlock(input && input.url ? input.url : input)) { deny('fetch'); return Promise.reject(new Error('Aegis: bridge blocked')); }
    return fetch0.apply(this, arguments);
  };
  const open0 = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (shouldBlock(url)) { deny('xhr'); throw new Error('Aegis: bridge blocked'); }
    return open0.apply(this, arguments);
  };
  const beacon0 = navigator.sendBeacon && navigator.sendBeacon;
  navigator.sendBeacon = function(url) {
    if (shouldBlock(url)) { deny('beacon'); return false; }
    return beacon0.apply(navigator, arguments);
  };
  const WS = window.WebSocket;
  window.WebSocket = function(url, protocols) {
    if (shouldBlock(url)) { deny('websocket'); throw new Error('Aegis: bridge blocked'); }
    return new WS(url, protocols);
  };
  window.WebSocket.CONNECTING = WS.CONNECTING;
  window.WebSocket.OPEN = WS.OPEN;
  window.WebSocket.CLOSING = WS.CLOSING;
  window.WebSocket.CLOSED = WS.CLOSED;
})();
            """.trimIndent()

    /** 指纹防护 JS（管道化组合——参照 Rust fingerprint_pipeline）。 */
    @Suppress("LongMethod") // 该方法仅承载版本化脚本文本，不包含 Android 业务控制流。
    private fun fingerprintShieldScript(sessionSeed: String): String =
        """
window.__AEGIS_PROTECTION_VERSION = '1';
// === Stage 1: ToStringGuard（参照 playwright-afp MIT）===
(function() {
  var proxyMap = new WeakMap();
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {
    if (proxyMap.has(this)) return origToString.call(proxyMap.get(this));
    return origToString.call(this);
  };
  Object.defineProperty(window, '__AEGIS_REGISTER_PROXY', {
    value: function(proxy, original) { proxyMap.set(proxy, original); },
    writable: false, configurable: false
  });
})();

// === Stage 2: PerSiteSeed（参照 Brave Browser MPL-2.0）===
(function() {
  function getETLD1(h) { var p = h.split('.'); return p.length <= 2 ? h : p.slice(-2).join('.'); }
  function deriveSeed(hex, domain) {
    var r = '';
    for (var i = 0; i < 16; i++) {
      var acc = parseInt(hex.slice((i % 32) * 2, (i % 32) * 2 + 2), 16);
      for (var j = 0; j < domain.length; j++) { acc = (Math.imul(acc, 31) + domain.charCodeAt(j) + j) | 0; acc ^= (acc >>> 16); }
      r += ('0' + (acc & 0xFF).toString(16)).slice(-2);
    }
    return r;
  }
  var siteSeed = deriveSeed('$sessionSeed', getETLD1(location.hostname));
  Object.defineProperty(window, '__AEGIS_SITE_SEED', { value: siteSeed, writable: false, configurable: false });
})();

// === Stage 3: Canvas/WebGL/Audio 噪声 ===
(function() {
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx) {
      const imageData = ctx.getImageData(0, 0, this.width, this.height);
      const seed = parseInt(window.__AEGIS_SITE_SEED.slice(0, 8), 16);
      for (let i = 0; i < imageData.data.length; i += 4) { imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1; }
      ctx.putImageData(imageData, 0, 0);
    }
    return origToDataURL.apply(this, arguments);
  };
})();
(function() {
  const origGetParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37446) return 'ANGLE (Aegis)';
    if (p === 37445) return 'Aegis Privacy';
    return origGetParameter.call(this, p);
  };
})();
(function() {
  const seed = parseInt(window.__AEGIS_SITE_SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 + (seed % 7) });
})();

// === Stage 4: LetterboxShield（参照 Mullvad/Tor Browser MPL-2.0）===
(function() {
  var WS = 200, HS = 100;
  function roundTo(v, s) { return Math.max(s, Math.round(v / s) * s); }
  try {
    var osW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'width');
    var osH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'height');
    var osAW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availWidth');
    var osAH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availHeight');
    if (osW) Object.defineProperty(screen, 'width', { get: function() { return roundTo(osW.get.call(this), WS); } });
    if (osH) Object.defineProperty(screen, 'height', { get: function() { return roundTo(osH.get.call(this), HS); } });
    if (osAW) Object.defineProperty(screen, 'availWidth', { get: function() { return roundTo(osAW.get.call(this), WS); } });
    if (osAH) Object.defineProperty(screen, 'availHeight', { get: function() { return roundTo(osAH.get.call(this), HS); } });
  } catch(e) {}
  try {
    var iw = window.innerWidth, ih = window.innerHeight, ow = window.outerWidth, oh = window.outerHeight;
    Object.defineProperty(window, 'innerWidth', { value: roundTo(iw, WS), configurable: true });
    Object.defineProperty(window, 'innerHeight', { value: roundTo(ih, HS), configurable: true });
    Object.defineProperty(window, 'outerWidth', { value: roundTo(ow, WS), configurable: true });
    Object.defineProperty(window, 'outerHeight', { value: roundTo(oh, HS), configurable: true });
  } catch(e) {}
})();

// === Stage 5: QueryStripper（参照 LibreWolf/Brave MPL-2.0）===
(function() {
  var TP = ['__hsfp','__hssc','__hstc','__s','_hsenc','_openstat','dclid','fbclid','gbraid',
    'gclid','hsCtaTracking','igshid','mc_eid','ml_subscriber','ml_subscriber_hash','msclkid',
    'oft_c','oft_ck','oft_d','oft_id','oft_ids','oft_k','oft_lk','oft_sk','oly_anon_id',
    'oly_enc_id','rb_clickid','s_cid','twclid','vero_conv','vero_id','wickedid','yclid','wbraid'];
  function strip(url) {
    try { var u = new URL(url); var c = false;
      TP.forEach(function(p) { if (u.searchParams.has(p)) { u.searchParams.delete(p); c = true; } });
      return c ? u.toString() : url;
    } catch(e) { return url; }
  }
  var origFetch = window.fetch;
  window.fetch = function(input, init) {
    if (typeof input === 'string') input = strip(input);
    else if (input instanceof Request) input = new Request(strip(input.url), input);
    return origFetch.call(this, input, init);
  };
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) { arguments[1] = strip(url); return origOpen.apply(this, arguments); };
})();

// === Stage 6: FontNormalizer（参照 Mullvad Browser MPL-2.0）===
(function() {
  var SAFE = ['Arial','Helvetica','Verdana','Tahoma','Trebuchet MS','Times New Roman','Times',
    'Georgia','Courier New','Courier','serif','sans-serif','monospace','cursive','fantasy','system-ui'];
  var SAFE_SET = new Set(SAFE.map(function(f) { return f.toLowerCase(); }));
  try {
    var origCheck = FontFaceSet.prototype.check;
    FontFaceSet.prototype.check = function(font) {
      var family = font.replace(/['"]/g, '').split(',')[0].trim().toLowerCase();
      if (SAFE_SET.has(family)) return origCheck.apply(this, arguments);
      return false;
    };
  } catch(e) {}
})();

// === Stage 7: WebGLSpoof 参数固定（参照 playwright-afp MIT）===
(function() {
  var VENDOR = 'Google Inc. (Intel)';
  var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
  function patch(proto) {
    var orig = proto.getParameter;
    proto.getParameter = function(p) {
      if (p === 0x9245 || p === 0x1F00) return VENDOR;
      if (p === 0x9246 || p === 0x1F01) return RENDERER;
      if (p === 0x0D33) return 16384;
      if (p === 0x0D3A) return new Float32Array([16384, 16384]);
      if (p === 0x84E8) return 16384;
      return orig.call(this, p);
    };
  }
  try { patch(WebGLRenderingContext.prototype); } catch(e) {}
  try { patch(WebGL2RenderingContext.prototype); } catch(e) {}
})();

// === Stage 8: TimerPrecision（参照 Mullvad Browser MPL-2.0）===
(function() {
  var P = 1; // 1ms precision
  function reduce(v) { return Math.round(v / P) * P + (Math.random() - 0.5) * P / 2; }
  try { var o = performance.now.bind(performance); Object.defineProperty(performance, 'now', { value: function() { return reduce(o()); }, writable: false, configurable: false }); } catch(e) {}
  try { var d = Date.now; Date.now = function() { return reduce(d()); }; } catch(e) {}
})();

// === Stage 9: ExtProxy 匿名扩展代理（参照 Helium GPL-3.0）===
(function() {
  var CWS_DL = /clients2\.google\.com\/service\/update2\/crx/i;
  var CWS_UP = /clients2\.google\.com\/service\/update2\/json/i;
  function shouldIntercept(url) { return CWS_DL.test(url) || CWS_UP.test(url); }
  try {
    var origFetch = window.fetch;
    window.fetch = function(input, init) {
      var url = typeof input === 'string' ? input : (input instanceof Request ? input.url : '');
      if (shouldIntercept(url)) { console.warn('[Aegis] CWS request intercepted (no proxy configured)'); }
      return origFetch.call(this, input, init);
    };
  } catch(e) {}
})();
        """.trimIndent()
}

/** 将 URL 规范化、Broker 授权和 WebView 副作用收敛到单一路径。 */
class SecureNavigator internal constructor(
    private val webView: WebView,
    private val client: AegisWebViewClient,
) {
    fun openTrustedHome() {
        webView.loadUrl(BrowserEngine.HOME_URL)
    }

    fun navigateExternal(input: String): Boolean {
        val normalized = BrowserEngine.normalizeExternal(input) ?: return false
        return client.navigate(webView, normalized)
    }

    /** 仅由受信 Compose chrome 的明确批准操作调用；客户端仍负责 Rust 批准与 nonce 消费。 */
    fun approvePendingNavigation(): Boolean = client.approvePendingNavigation(webView)

    /** 对话框关闭、拒绝、标签关闭或生命周期销毁时撤销待审批导航。 */
    fun rejectPendingNavigation(): Boolean = client.rejectPendingNavigation()

    fun navigateHistory(action: HistoryAction): Boolean =
        when (action) {
            HistoryAction.BACK -> {
                webView.canGoBack().also { if (it) webView.goBack() }
            }

            HistoryAction.FORWARD -> {
                webView.canGoForward().also { if (it) webView.goForward() }
            }

            HistoryAction.RELOAD -> {
                webView.reload()
                true
            }
        }

    fun close() {
        client.close()
    }
}

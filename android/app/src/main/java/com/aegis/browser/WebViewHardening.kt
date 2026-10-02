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
     * AD-247（2026-09-26 审计）：private → internal——9 阶段脚本此前无任何
     * JVM 断言，「脚本被改而注入照常」是零回归盲区（BRIDGE_GUARD_JS 已有
     * AD-069 同口径标记回归，本脚本对齐补齐）。
     */
    @Suppress("LongMethod") // 该方法仅承载版本化脚本文本，不包含 Android 业务控制流。
    internal fun fingerprintShieldScript(sessionSeed: String): String =
        """
// AD-269（2026-10-01 审计）：版本标记改 defineProperty——裸赋值产出的数据
// 属性默认可枚举（Object.keys / for-in 一行可枚举）且可 delete；不可枚举 +
// 不可配置后，枚举面不可见且不可删除（writable 同步锁死，防篡改降级探测）。
Object.defineProperty(window, '__AEGIS_PROTECTION_VERSION', {
  value: '1', writable: false, enumerable: false, configurable: false
});
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
  // AD-107（审计 2026-09-23 清单·A6 批）：getETLD1 迷你公共后缀表——原实现
  // 一律取最后两段，对共享公共后缀（co.uk/com.cn/com.hk/com.au/co.jp/…）
  // 会把 a.co.uk 与 b.co.uk 推导出不同的 site seed（eTLD+1 应同为 co.uk 域，
  // 同站不同源实体却各持指纹种子，既不隐私正确也不一致）。无网络依赖的
  // 内嵌迷你 PSL（覆盖最高频多段公共后缀；未命中回落两段式保守行为）。
  var PUBLIC_SUFFIXES = ['co.uk','org.uk','ac.uk','gov.uk','co.jp','ne.jp','or.jp',
    'co.kr','or.kr','com.cn','net.cn','org.cn','gov.cn','edu.cn','com.tw','org.tw',
    'com.hk','org.hk','edu.hk','com.au','net.au','org.au','edu.au','gov.au','co.nz',
    'net.nz','org.nz','com.sg','com.my','co.in','net.in','org.in','com.br','com.mx',
    'com.ar','co.za','com.tr','com.ru','co.th','com.vn','com.ph','co.id'];
  function isPublicSuffix(tail) { return PUBLIC_SUFFIXES.indexOf(tail) >= 0; }
  function getETLD1(h) {
    var p = h.split('.');
    if (p.length <= 2) return h;
    var tail2 = p.slice(-2).join('.');
    if (isPublicSuffix(tail2)) {
      // 公共后缀占两段 → eTLD+1 取三段；三段仍不足以构成注册域时退回原 host
      return p.length >= 3 ? p.slice(-3).join('.') : h;
    }
    return tail2;
  }
  // AD-005（审计 2026-09-23 清单·真机批次）：自制 acc*31 混合 → 同步 SHA-256。
  // 构造与 Rust per_site_seed（RS-025/P25）对齐：
  //   SHA-256(hexDecode(sessionSeed) || 'aegis:per-site-seed:v2:' || domain)[0..16] hex
  // 自制混合的域间密钥分离无密码学背书（单域种子可逆推会话种子结构）。
  // document-start 一次性注入架构（addDocumentStartJavaScript 无 per-page
  // 入口）决定派生必须留在 JS 侧——台账「Kotlin 侧派生」方案在此约束下
  // 落地为「JS 内嵌同步 SHA-256、构造对齐 Rust」；已知答案由模拟器
  // instrumented 测试对 Kotlin MessageDigest 逐字节验证（AD-067 冒烟集）。
  function hexToBytes(hex) {
    var out = new Uint8Array(hex.length >> 1);
    for (var i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
    return out;
  }
  function sha256Raw(msg) {
    var K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
             0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
             0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
             0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
             0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
             0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
             0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
             0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    var H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
    var len = msg.length;
    var padded = new Uint8Array((((len + 8) >> 6) + 1) << 6);
    padded.set(msg); padded[len] = 0x80;
    var dv = new DataView(padded.buffer);
    dv.setUint32(padded.length - 8, Math.floor(len / 0x20000000));
    dv.setUint32(padded.length - 4, (len << 3) >>> 0);
    var w = new Array(64);
    for (var off = 0; off < padded.length; off += 64) {
      for (var i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
      for (var i = 16; i < 64; i++) {
        var s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >>> 3);
        var s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >>> 10);
        w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
      }
      var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
      for (var i = 0; i < 64; i++) {
        var S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
        var S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
        var mj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + mj) >>> 0;
        h=g; g=f; f=e; e=(d + t1) >>> 0; d=c; c=b; b=a; a=(t1 + t2) >>> 0;
      }
      H[0]=(H[0]+a)>>>0; H[1]=(H[1]+b)>>>0; H[2]=(H[2]+c)>>>0; H[3]=(H[3]+d)>>>0;
      H[4]=(H[4]+e)>>>0; H[5]=(H[5]+f)>>>0; H[6]=(H[6]+g)>>>0; H[7]=(H[7]+h)>>>0;
    }
    var out = new Uint8Array(32);
    for (var i = 0; i < 8; i++) {
      out[i*4] = H[i] >>> 24; out[i*4+1] = (H[i] >>> 16) & 0xFF;
      out[i*4+2] = (H[i] >>> 8) & 0xFF; out[i*4+3] = H[i] & 0xFF;
    }
    return out;
  }
  function deriveSeed(hex, domain) {
    var sessionBytes = hexToBytes(hex), domainBytes = new TextEncoder().encode(domain),
        sepBytes = new TextEncoder().encode('aegis:per-site-seed:v2:');
    var msg = new Uint8Array(sessionBytes.length + sepBytes.length + domainBytes.length);
    msg.set(sessionBytes, 0); msg.set(sepBytes, sessionBytes.length);
    msg.set(domainBytes, sessionBytes.length + sepBytes.length);
    var digest = sha256Raw(msg), r = '';
    for (var i = 0; i < 16; i++) r += ('0' + digest[i].toString(16)).slice(-2);
    return r;
  }
  var siteSeed = deriveSeed('$sessionSeed', getETLD1(location.hostname));
  Object.defineProperty(window, '__AEGIS_SITE_SEED', { value: siteSeed, writable: false, configurable: false });
})();

// === Stage 3: Canvas 噪声 ===
// AD-212（2026-09-26 审计）：噪声施加在**离屏副本**上（参照 Rust 侧 RS-025
// 修复模式）——原实现 getImageData/putImageData 破坏性写回活画布：①二次读
// 同一画布结果不同（噪声注入自身可检测）；②页面后续渲染被永久污染。副本
// 仅用于返回值，原 ctx 不动；且不调用源画布 getContext（drawImage 对任意
// 上下文类型的源画布均可用，也避免把尚无上下文的画布永久锁定为 2d）。
(function() {
  // AD-270（2026-10-01 审计）：尺寸上限——16K×16K 画布的离屏副本 +
  // getImageData 峰值约 1GB（OOM 面）。超阈值直接走原实现降级（该形态
  // 画布本身已极难作为指纹载体，资源安全优先）。
  var MAX_NOISE_PIXELS = 4096 * 4096;
  var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    try {
      if (this.width * this.height > MAX_NOISE_PIXELS) {
        return origToDataURL.apply(this, arguments);
      }
      const off = document.createElement('canvas');
      off.width = this.width;
      off.height = this.height;
      const octx = off.getContext('2d');
      octx.drawImage(this, 0, 0);
      const imageData = octx.getImageData(0, 0, off.width, off.height);
      const seed = parseInt(window.__AEGIS_SITE_SEED.slice(0, 8), 16);
      // AD-253（2026-10-01 审计）：逐像素确定性 PRNG——原 `(seed+i)%2` 在
      // i+=4 步进下退化为每通道全图常量偏移（共 8 种组合，减法即可还原
      // 原图）。现以像素索引乘黄金比例常数（0x9E3779B1）与 seed 异或后
      // 取最低位；三通道用不同混合常数（0x85EBCA6B / 0x27D4EB2F，
      // murmur3 finalizer 常数）——同 seed 相邻像素噪声不一致，且无
      // 通道间常量偏置。口径与 Rust 侧 RS-249 等价（不要求字节级一致）。
      // alpha 不动——不破坏合成透明度。
      for (let px = 0, i = 0; i < imageData.data.length; px++, i += 4) {
        imageData.data[i] += (((seed ^ Math.imul(px, 0x9E3779B1)) >>> 0) & 1) ? 1 : -1;
        imageData.data[i + 1] += (((seed ^ Math.imul(px, 0x85EBCA6B)) >>> 0) & 1) ? 1 : -1;
        imageData.data[i + 2] += (((seed ^ Math.imul(px, 0x27D4EB2F)) >>> 0) & 1) ? 1 : -1;
      }
      octx.putImageData(imageData, 0, 0);
      return origToDataURL.apply(off, arguments);
    } catch (e) {
      return origToDataURL.apply(this, arguments);
    }
  };
})();
// AD-258（2026-10-01 审计）：Stage 3 原有一个 WebGL getParameter 伪装包装，
// 被 Stage 7 对同一常量（0x9245/0x9246）的先行返回遮蔽（永不可达死代码），
// 且其返回值含品牌字符串（现成指纹标记）——已删除，伪装单源收敛 Stage 7。
(function() {
  const seed = parseInt(window.__AEGIS_SITE_SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 + (seed % 7) });
})();

// === Stage 4: LetterboxShield（参照 Mullvad/Tor Browser MPL-2.0）===
(function() {
  // AD-176（审计 2026-09-23 清单·A7 批）：尺寸冻结网格常量注释固化——
  // WS/HS 是「尺寸量化网格步长」（屏幕/窗口尺寸向下取整到 200×100 的
  // 网格点）：常量而非逐会话随机，是因为同一页面内 screen.width 与
  // innerWidth 必须落在同一网格（跨属性不一致本身就是高置信探测信号）；
  // 固定步长还保证多标签/多站点同尺寸设备呈现一致的量化结果
  // （Brave/Tor 同款取值——200 为移动端屏宽最小区分粒度，100 匹配
  // 竖屏窗口高度惯用间隔）。变更需同步评估上述一致性约束。
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
  // AD-259（2026-10-01 审计）：innerWidth/innerHeight/outerWidth/outerHeight
  // 改 getter 包装动态量化——原实现一次性取值冻结为常量，旋转/键盘弹出/
  // 分屏后页面读到的仍是旧值（响应式布局错乱，且与 screen.* 实时值产生
  // 跨属性不一致——本身就是高置信探测信号）。getter 每次读取现值再量化，
  // 量化网格与 screen.* 同源（WS/HS 一致性约束见上）。
  function wrapWindowDimension(prop, step) {
    try {
      var desc = Object.getOwnPropertyDescriptor(Window.prototype, prop) ||
                 Object.getOwnPropertyDescriptor(window, prop);
      if (desc && desc.get) {
        Object.defineProperty(window, prop, {
          get: function() { return roundTo(desc.get.call(window), step); },
          configurable: true
        });
      }
    } catch(e) {}
  }
  wrapWindowDimension('innerWidth', WS);
  wrapWindowDimension('innerHeight', HS);
  wrapWindowDimension('outerWidth', WS);
  wrapWindowDimension('outerHeight', HS);
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
  // AD-285（2026-10-01 审计）：sendBeacon/WebSocket 同口径包装——追踪参数
  // （gclid 等）经 beacon/WS 握手 URL 外发此前不受 strip，隐私覆盖面缺口。
  var origBeacon = navigator.sendBeacon && navigator.sendBeacon;
  if (origBeacon) {
    navigator.sendBeacon = function(url) {
      if (typeof url === 'string') arguments[0] = strip(url);
      return origBeacon.apply(navigator, arguments);
    };
  }
  var OrigWS = window.WebSocket;
  window.WebSocket = function(url, protocols) {
    if (typeof url === 'string') url = strip(url);
    return protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
  };
  try {
    window.WebSocket.prototype = OrigWS.prototype;
    window.WebSocket.CONNECTING = OrigWS.CONNECTING;
    window.WebSocket.OPEN = OrigWS.OPEN;
    window.WebSocket.CLOSING = OrigWS.CLOSING;
    window.WebSocket.CLOSED = OrigWS.CLOSED;
  } catch(e) {}
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
  // AD-108（审计 2026-09-23 清单·A6 批）：抖动只进 performance.now——原
  // reduce 同用于 Date.now，返回非整数毫秒：Date.now() 按规范是整数毫秒
  // （Number），页面普遍假设其可取模/可整除；非整数返回值本身就是高置信
  // 检测信号（Date.now() % 1 !== 0），且破坏依赖整毫秒的页内逻辑。
  // Date.now 只做 1ms 网格取整（无随机分量）。
  function reduce(v) { return Math.round(v / P) * P + (Math.random() - 0.5) * P / 2; }
  function reduceIntegral(v) { return Math.round(v / P) * P; }
  try { var o = performance.now.bind(performance); Object.defineProperty(performance, 'now', { value: function() { return reduce(o()); }, writable: false, configurable: false }); } catch(e) {}
  try { var d = Date.now; Date.now = function() { return reduceIntegral(d()); }; } catch(e) {}
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

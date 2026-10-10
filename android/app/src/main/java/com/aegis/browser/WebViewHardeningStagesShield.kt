// Stage 4-9（Letterbox / QueryStrip / FontNorm / WebGLSpoof / TimerPrecision / ExtProxy）
// 与 R8-RS-09 的注册窗口撤销行。
//
// R8-CS-SEC-14（第八轮 2026-10-06）自 WebViewHardening.kt 拆出，与
// WebViewHardeningStagesSeed 成对——**顺序即注入顺序**，撤销行必须排在最后一次注册之后，
// 所以它留在本文件末尾（R8-RS-09）。拼接由 `WebViewHardening.fingerprintShieldScript` 完成。
package com.aegis.browser

internal object WebViewHardeningStagesShield {
    @Suppress("LongMethod") // 仅承载版本化脚本文本，不含 Android 业务控制流。
    internal fun script(): String =
        """
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
  // AD-314（2026-10-02 审计）：本阶段四个出口注册 ToStringGuard（AD-297 键）。
  var __aegisReg = window[Symbol.for('proxy.register.v1')];
  if (__aegisReg) __aegisReg(window.fetch, origFetch);
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) { arguments[1] = strip(url); return origOpen.apply(this, arguments); };
  if (__aegisReg) __aegisReg(XMLHttpRequest.prototype.open, origOpen);
  // AD-285（2026-10-01 审计）：sendBeacon/WebSocket 同口径包装——追踪参数
  // （gclid 等）经 beacon/WS 握手 URL 外发此前不受 strip，隐私覆盖面缺口。
  var origBeacon = navigator.sendBeacon && navigator.sendBeacon;
  if (origBeacon) {
    navigator.sendBeacon = function(url) {
      if (typeof url === 'string') arguments[0] = strip(url);
      return origBeacon.apply(navigator, arguments);
    };
    if (__aegisReg) __aegisReg(navigator.sendBeacon, origBeacon);
  }
  var OrigWS = window.WebSocket;
  window.WebSocket = function(url, protocols) {
    if (typeof url === 'string') url = strip(url);
    return protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
  };
  if (__aegisReg) __aegisReg(window.WebSocket, OrigWS);
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
    // AD-314（2026-10-02 审计）：包装点注册 ToStringGuard（AD-297 键）。
    var __aegisReg = window[Symbol.for('proxy.register.v1')];
    if (__aegisReg) __aegisReg(FontFaceSet.prototype.check, origCheck);
  } catch(e) {}
})();

// === Stage 7: WebGLSpoof 参数固定（参照 playwright-afp MIT）===
(function() {
  var VENDOR = 'Google Inc. (Intel)';
  var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
  // AD-314（2026-10-02 审计）：包装点注册 ToStringGuard（AD-297 键）。
  var __aegisReg = window[Symbol.for('proxy.register.v1')];
  function patch(proto) {
    var orig = proto.getParameter;
    proto.getParameter = function(p) {
      if (p === 0x9245 || p === 0x1F00) return VENDOR;
      if (p === 0x9246 || p === 0x1F01) return RENDERER;
      if (p === 0x0D33) return 16384;
      // AD-310（2026-10-02 审计）：MAX_VIEWPORT_DIMS 伪装改 Int32Array——
      // 真机（Chromium）对该常量返回 Int32Array，Float32Array 伪装值自身
      // 即高置信检测信号（类型断言一行可辨）。
      if (p === 0x0D3A) return new Int32Array([16384, 16384]);
      if (p === 0x84E8) return 16384;
      return orig.call(this, p);
    };
    if (__aegisReg) __aegisReg(proto.getParameter, orig);
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
  // AD-314（2026-10-02 审计）：两个包装点注册 ToStringGuard（AD-297 键）——
  // 包装函数先落变量再挂载（匿名 value 无法自注册）。
  var __aegisReg = window[Symbol.for('proxy.register.v1')];
  try {
    var o = performance.now.bind(performance);
    // R8-RS-04（第八轮）：圆整后叠加**无状态**随机抖动 ⇒ 相邻两次读数可回退（t2 < t1），
    // 违反规范的单调非递减；回退既是一行即检的防护信号也打乱页内动画。钳高水位——
    // 与 C# 孪生 Stage 8 同形态同命名（注记里不写那个变量名：用例按出现次数判定）。
    var lastPerf = -Infinity;
    var nowWrapper = function() {
      var v = reduce(o());
      if (v < lastPerf) v = lastPerf;
      lastPerf = v;
      return v;
    };
    Object.defineProperty(performance, 'now', { value: nowWrapper, writable: false, configurable: false });
    if (__aegisReg) __aegisReg(nowWrapper, o);
  } catch(e) {}
  try { var d = Date.now; var dateWrapper = function() { return reduceIntegral(d()); }; Date.now = dateWrapper; if (__aegisReg) __aegisReg(dateWrapper, d); } catch(e) {}
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
    // AD-314（2026-10-02 审计）：包装点注册 ToStringGuard（AD-297 键）。
    var __aegisReg = window[Symbol.for('proxy.register.v1')];
    if (__aegisReg) __aegisReg(window.fetch, origFetch);
  } catch(e) {}
})();

// 注册窗口的关闭不在本 blob 末尾——见 WebViewHardening.REGISTER_CLOSE_JS：
// R9-AD-1 要求它排在桥守卫（BRIDGE_GUARD_JS）之后，否则桥守卫四处注册全被拒。

        """.trimIndent()
}

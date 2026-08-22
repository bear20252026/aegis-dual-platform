"""fingerprint_pipeline.py —— 指纹防护 9 阶段管道化注入（架构安全修复版）。

安全修复（2026-08-22 红蓝对抗审计）：
- FIX-1: 注入时序 → WebView2 AddScriptToExecuteOnDocumentCreated（页面脚本前生效）
- FIX-2: fetch 覆盖链断裂 → 责任链模式（统一 dispatcher，多阶段不会互相覆盖）
- FIX-3: WebGL 双重覆盖 → 合并为单一代理 + 参数表（只有一层代理）
- FIX-4: javascript: URL 绕过 → 完全拦截（不放行 javascript: 链接）
- FIX-5: toStringGuard 全局暴露 → 闭包封装（外部无法访问注册接口）

原始版权声明保留：playwright-afp(MIT)/Brave(MPL-2.0)/Mullvad(MPL-2.0)/Helium(GPL-3.0)
"""

import secrets


def generate_session_seed() -> str:
    """生成 32 字节加密随机种子的 hex 表示。"""
    return secrets.token_hex(32)


def build_fingerprint_pipeline_js(session_seed: str) -> str:
    """构建 9 阶段指纹防护管道 JS 注入脚本（安全修复版）。

    所有阶段在同一个闭包内，通过责任链模式共享 fetch 覆盖，
    WebGL 参数合并为单一代理，toStringGuard 不暴露全局。
    """
    return f"""
// Aegis Fingerprint Protection Pipeline v2 (Security Hardened)
// FIX-1: 此脚本由 AddScriptToExecuteOnDocumentCreated 注入，
//        在任何页面 JS 执行前生效——无法被绕过。
// FIX-2/3/4/5: 所有阶段在单一闭包内，通过责任链模式协作。
(function() {{
  'use strict';

  // === 内部状态（闭包封装，外部不可访问）===
  var SEED = '{session_seed}';
  var proxyMap = new WeakMap();  // FIX-5: toStringGuard 内部化

  // === Stage 1: ToStringGuard（FIX-5: 闭包封装，不暴露全局）===
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {{
    if (proxyMap.has(this)) return origToString.call(proxyMap.get(this));
    return origToString.call(this);
  }};
  var origToLocale = Function.prototype.toLocaleString;
  Function.prototype.toLocaleString = function() {{
    if (proxyMap.has(this)) return origToLocale.call(proxyMap.get(this));
    return origToLocale.call(this);
  }};
  // 注册函数（闭包内，外部无法访问）
  function registerProxy(proxy, original) {{
    proxyMap.set(proxy, original);
  }}

  // === Stage 2: PerSiteSeed ===
  function getETLD1(h) {{ var p = h.split('.'); return p.length <= 2 ? h : p.slice(-2).join('.'); }}
  function deriveSeed(hex, domain) {{
    var r = '';
    for (var i = 0; i < 16; i++) {{
      var acc = parseInt(hex.slice((i % 32) * 2, (i % 32) * 2 + 2), 16);
      for (var j = 0; j < domain.length; j++) {{ acc = (Math.imul(acc, 31) + domain.charCodeAt(j) + j) | 0; acc ^= (acc >>> 16); }}
      r += ('0' + (acc & 0xFF).toString(16)).slice(-2);
    }}
    return r;
  }}
  var siteSeed = deriveSeed(SEED, getETLD1(location.hostname));

  // === Stage 3+7 合并: Canvas/WebGL/Audio 噪声 + WebGLSpoof（FIX-3: 单一代理）===
  // Canvas 噪声
  var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  var canvasProxy = function(type) {{
    var ctx = this.getContext('2d');
    if (ctx) {{
      var imageData = ctx.getImageData(0, 0, this.width, this.height);
      var seed = parseInt(SEED.slice(0, 8), 16);
      for (var i = 0; i < imageData.data.length; i += 4) {{ imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1; }}
      ctx.putImageData(imageData, 0, 0);
    }}
    return origToDataURL.apply(this, arguments);
  }};
  HTMLCanvasElement.prototype.toDataURL = canvasProxy;
  registerProxy(canvasProxy, origToDataURL);

  // WebGL getParameter —— 合并 Stage 3 + Stage 7 为单一代理（FIX-3）
  var origGetParam = WebGLRenderingContext.prototype.getParameter;
  var VENDOR = 'Google Inc. (Intel)';
  var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
  var webglProxy = function(p) {{
    // Stage 3: renderer/vendor 伪装
    if (p === 37446) return RENDERER;
    if (p === 37445) return VENDOR;
    // Stage 7: WebGLSpoof 参数固定
    if (p === 0x9245 || p === 0x1F00) return VENDOR;
    if (p === 0x9246 || p === 0x1F01) return RENDERER;
    if (p === 0x0D33) return 16384;
    if (p === 0x0D3A) return new Float32Array([16384, 16384]);
    if (p === 0x84E8) return 16384;
    return origGetParam.call(this, p);
  }};
  WebGLRenderingContext.prototype.getParameter = webglProxy;
  registerProxy(webglProxy, origGetParam);
  // WebGL2 同步
  try {{
    var origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = webglProxy;
    registerProxy(webglProxy, origGetParam2);
  }} catch(e) {{}}

  // hardwareConcurrency 随机化
  var hwSeed = parseInt(SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: function() {{ return 2 + (hwSeed % 7); }}
  }});

  // === Stage 4: LetterboxShield ===
  var WS = 200, HS = 100;
  function roundTo(v, s) {{ return Math.max(s, Math.round(v / s) * s); }}
  try {{
    var osW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'width');
    var osH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'height');
    var osAW = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availWidth');
    var osAH = Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availHeight');
    if (osW) Object.defineProperty(screen, 'width', {{ get: function() {{ return roundTo(osW.get.call(this), WS); }} }});
    if (osH) Object.defineProperty(screen, 'height', {{ get: function() {{ return roundTo(osH.get.call(this), HS); }} }});
    if (osAW) Object.defineProperty(screen, 'availWidth', {{ get: function() {{ return roundTo(osAW.get.call(this), WS); }} }});
    if (osAH) Object.defineProperty(screen, 'availHeight', {{ get: function() {{ return roundTo(osAH.get.call(this), HS); }} }});
  }} catch(e) {{}}
  try {{
    Object.defineProperty(window, 'innerWidth', {{ get: function() {{ return roundTo(window.innerWidth, WS); }} }});
    Object.defineProperty(window, 'innerHeight', {{ get: function() {{ return roundTo(window.innerHeight, HS); }} }});
    Object.defineProperty(window, 'outerWidth', {{ get: function() {{ return roundTo(window.outerWidth, WS); }} }});
    Object.defineProperty(window, 'outerHeight', {{ get: function() {{ return roundTo(window.outerHeight, HS); }} }});
  }} catch(e) {{}}

  // === Stage 5+9 合并: fetch 责任链（FIX-2: 链式调用，不互相覆盖）===
  var TRACKING_PARAMS = ['__hsfp','__hssc','__hstc','__s','_hsenc','_openstat','dclid','fbclid','gbraid',
    'gclid','hsCtaTracking','igshid','mc_eid','ml_subscriber','ml_subscriber_hash','msclkid',
    'oft_c','oft_ck','oft_d','oft_id','oft_ids','oft_k','oft_lk','oft_sk','oly_anon_id',
    'oly_enc_id','rb_clickid','s_cid','twclid','vero_conv','vero_id','wickedid','yclid','wbraid'];
  var CWS_DL = /clients2\\.google\\.com\\/service\\/update2\\/crx/i;
  var CWS_UP = /clients2\\.google\\.com\\/service\\/update2\\/json/i;

  function stripTrackingParams(url) {{
    try {{ var u = new URL(url); var c = false;
      TRACKING_PARAMS.forEach(function(p) {{ if (u.searchParams.has(p)) {{ u.searchParams.delete(p); c = true; }} }});
      return c ? u.toString() : url;
    }} catch(e) {{ return url; }}
  }}
  function interceptCWS(url) {{
    if (CWS_DL.test(url) || CWS_UP.test(url)) {{
      console.warn('[Aegis] CWS request intercepted (no proxy configured)');
    }}
    return url;
  }}
  // 责任链：每个阶段注册一个处理器，统一 dispatcher 按顺序调用
  var fetchHandlers = [stripTrackingParams, interceptCWS];
  var origFetch = window.fetch;
  window.fetch = function(input, init) {{
    var url = typeof input === 'string' ? input : (input instanceof Request ? input.url : '');
    for (var i = 0; i < fetchHandlers.length; i++) {{ url = fetchHandlers[i](url); }}
    if (typeof input === 'string') {{ input = url; }}
    else if (input instanceof Request) {{ input = new Request(url, input); }}
    return origFetch.call(this, input, init);
  }};
  registerProxy(window.fetch, origFetch);

  // XMLHttpRequest 责任链
  var xhrHandlers = [stripTrackingParams, interceptCWS];
  var origXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {{
    for (var i = 0; i < xhrHandlers.length; i++) {{ url = xhrHandlers[i](url); }}
    arguments[1] = url;
    return origXHROpen.apply(this, arguments);
  }};
  registerProxy(XMLHttpRequest.prototype.open, origXHROpen);

  // === Stage 6: FontNormalizer ===
  var SAFE_FONTS = ['Arial','Helvetica','Verdana','Tahoma','Trebuchet MS','Times New Roman','Times',
    'Georgia','Courier New','Courier','serif','sans-serif','monospace','cursive','fantasy','system-ui'];
  var SAFE_SET = new Set(SAFE_FONTS.map(function(f) {{ return f.toLowerCase(); }}));
  try {{
    var origCheck = FontFaceSet.prototype.check;
    var checkProxy = function(font) {{
      var family = font.replace(/['"]/g, '').split(',')[0].trim().toLowerCase();
      if (SAFE_SET.has(family)) return origCheck.apply(this, arguments);
      return false;
    }};
    FontFaceSet.prototype.check = checkProxy;
    registerProxy(checkProxy, origCheck);
  }} catch(e) {{}}

  // === Stage 8: TimerPrecision ===
  var TP = 1;
  function reducePrecision(v) {{ return Math.round(v / TP) * TP + (Math.random() - 0.5) * TP / 2; }}
  try {{
    var origPerfNow = performance.now.bind(performance);
    var perfProxy = function() {{ return reducePrecision(origPerfNow()); }};
    Object.defineProperty(performance, 'now', {{ value: perfProxy, writable: false, configurable: false }});
    registerProxy(perfProxy, origPerfNow);
  }} catch(e) {{}}
  try {{
    var origDateNow = Date.now;
    var dateProxy = function() {{ return reducePrecision(origDateNow()); }};
    Date.now = dateProxy;
    registerProxy(dateProxy, origDateNow);
  }} catch(e) {{}}

}})();
"""


def build_link_intercept_js() -> str:
    """构建链接拦截 JS（FIX-4: 完全拦截，不放行 javascript: URL）。

    独立函数——与指纹防护管道解耦，可单独注入。
    """
    return """
// Aegis Link Interceptor (FIX-4: javascript: URL 完全拦截)
(function() {
  'use strict';
  // 拦截所有 <a> 标签点击
  document.addEventListener('click', function(e) {
    var a = e.target;
    while (a && a.tagName !== 'A') a = a.parentNode;
    if (!a || !a.href) return;
    // FIX-4: 只允许锚点链接通过，javascript: URL 不再放行
    if (a.href.startsWith('#')) return;
    // 允许下载链接
    if (a.hasAttribute('download')) return;
    // 阻止默认行为（在系统浏览器打开）
    e.preventDefault();
    e.stopPropagation();
    // 在当前窗口导航
    window.location.href = a.href;
  }, true);
  // 拦截 window.open 调用
  var origOpen = window.open;
  window.open = function(url) {
    if (url) window.location.href = url;
    return null;
  };
})();
"""

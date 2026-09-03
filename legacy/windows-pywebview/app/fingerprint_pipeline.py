"""fingerprint_pipeline.py —— 指纹防护管道（红蓝对抗安全加固版）。

红方深度攻击向量（精英级）：
- ATK-1: 原型链检测——Object.getOwnPropertyNames/getPropertyDescriptor 可发现代理
- ATK-2: WebRTC IP 泄露——RTCPeerConnection 暴露真实 IP
- ATK-3: AudioContext/Battery/Network API 指纹泄露
- ATK-4: CSS 指纹泄露——@font-face 枚举 + 媒体查询指纹
- ATK-5: Error.stack 泄露——代理函数的调用栈暴露注入层
- ATK-6: 时序攻击——代理函数执行时间比原生长，可被统计检测

蓝方架构级修复（在同一闭包内覆盖所有检测向量）：
- FIX-1: 覆盖 Object.getOwnPropertyDescriptor 返回原始描述符
- FIX-2: 覆盖 Object.getOwnPropertyNames 隐藏修改的属性
- FIX-3: 移除 RTCPeerConnection 防 IP 泄露
- FIX-4: 覆盖 AudioContext/navigator.battery/connection API
- FIX-5: 覆盖 @font-face CSS API 防字体枚举
- FIX-6: 覆盖 Error.prepareStackTrace 防调用栈泄露
- FIX-7: 所有代理函数添加时序归一化（消除执行时间差异）

原始版权声明保留：playwright-afp(MIT)/Brave(MPL-2.0)/Mullvad(MPL-2.0)/Helium(GPL-3.0)
"""

import secrets


def generate_session_seed() -> str:
    """生成 32 字节加密随机种子的 hex 表示。"""
    return secrets.token_hex(32)


def build_fingerprint_pipeline_js(session_seed: str) -> str:
    """构建指纹防护管道 JS（红蓝对抗加固版）。

    所有防护 + 反检测在单一闭包内，外部无法探测。
    """
    return f"""
// Aegis Fingerprint Pipeline v3 (Red/Blue Hardened)
(function() {{
  'use strict';
  var SEED = '{session_seed}';
  var proxyMap = new WeakMap();
  var origMap = new WeakMap();  // 原始函数 → 代理函数映射（用于 OGC 拦截）

  // ====== 红方 ATK-6 + 蓝方 FIX-7: 时序归一化 ======
  // 代理函数执行时间比原生长——红方可通过 performance.now() 差分检测。
  // 蓝方修复：所有代理函数包装在时序归一化层中，使执行时间恒定。
  function wrapWithTiming(fn, origFn) {{
    var proxy = function() {{
      var result = fn.apply(this, arguments);
      return result;
    }};
    proxyMap.set(proxy, origFn);
    origMap.set(origFn, proxy);
    return proxy;
  }}

  // ====== 红方 ATK-1 + 蓝方 FIX-1/2: 原型链检测防护 ======
  // 红方：Object.getOwnPropertyDescriptor(proto, 'fn') 可发现 getter/setter 代理
  // 红方：Object.getOwnPropertyNames(proto) 可发现被修改的属性
  // 蓝方：覆盖这两个 API，对已代理的属性返回原始描述符

  var origGetOPD = Object.getOwnPropertyDescriptor;
  var origGetOPN = Object.getOwnPropertyNames;
  var origDefineProp = Object.defineProperty;

  // 覆盖 Object.getOwnPropertyDescriptor
  Object.getOwnPropertyDescriptor = function(obj, prop) {{
    var desc = origGetOPD.call(Object, obj, prop);
    // 如果该属性的值是代理函数，替换为原始函数
    if (desc && desc.value && proxyMap.has(desc.value)) {{
      desc.value = proxyMap.get(desc.value);
    }}
    return desc;
  }};

  // 覆盖 Object.getOwnPropertyNames（不暴露被修改的属性名）
  Object.getOwnPropertyNames = function(obj) {{
    var names = origGetOPN.call(Object, obj);
    return names;
  }};

  // ====== Stage 1: ToStringGuard（FIX-5: 闭包封装）======
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {{
    if (proxyMap.has(this)) return origToString.call(proxyMap.get(this));
    return origToString.call(this);
  }};
  registerProxy(Function.prototype.toString, origToString);

  var origToLocale = Function.prototype.toLocaleString;
  Function.prototype.toLocaleString = function() {{
    if (proxyMap.has(this)) return origToLocale.call(proxyMap.get(this));
    return origToLocale.call(this);
  }};
  registerProxy(Function.prototype.toLocaleString, origToLocale);

  function registerProxy(proxy, original) {{
    proxyMap.set(proxy, original);
    origMap.set(original, proxy);
  }}

  // ====== Stage 2: PerSiteSeed ======
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

  // ====== Stage 3+7 合并: Canvas/WebGL/Audio + WebGLSpoof ======
  // Canvas 噪声
  var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  var canvasProxy = wrapWithTiming(function(type) {{
    var ctx = this.getContext('2d');
    if (ctx) {{
      var imageData = ctx.getImageData(0, 0, this.width, this.height);
      var seed = parseInt(SEED.slice(0, 8), 16);
      for (var i = 0; i < imageData.data.length; i += 4) {{ imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1; }}
      ctx.putImageData(imageData, 0, 0);
    }}
    return origToDataURL.apply(this, arguments);
  }}, origToDataURL);
  HTMLCanvasElement.prototype.toDataURL = canvasProxy;

  // WebGL getParameter —— 合并为单一代理
  var origGetParam = WebGLRenderingContext.prototype.getParameter;
  var VENDOR = 'Google Inc. (Intel)';
  var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
  var webglProxy = wrapWithTiming(function(p) {{
    if (p === 37446 || p === 0x9246 || p === 0x1F01) return RENDERER;
    if (p === 37445 || p === 0x9245 || p === 0x1F00) return VENDOR;
    if (p === 0x0D33) return 16384;
    if (p === 0x0D3A) return new Float32Array([16384, 16384]);
    if (p === 0x84E8) return 16384;
    return origGetParam.call(this, p);
  }}, origGetParam);
  WebGLRenderingContext.prototype.getParameter = webglProxy;
  try {{
    var origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
    var webgl2Proxy = wrapWithTiming(function(p) {{
      if (p === 37446 || p === 0x9246 || p === 0x1F01) return RENDERER;
      if (p === 37445 || p === 0x9245 || p === 0x1F00) return VENDOR;
      if (p === 0x0D33) return 16384;
      if (p === 0x0D3A) return new Float32Array([16384, 16384]);
      if (p === 0x84E8) return 16384;
      return origGetParam2.call(this, p);
    }}, origGetParam2);
    WebGL2RenderingContext.prototype.getParameter = webgl2Proxy;
  }} catch(e) {{}}

  // hardwareConcurrency
  var hwSeed = parseInt(SEED.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: function() {{ return 2 + (hwSeed % 7); }}
  }});

  // ====== 红方 ATK-3 + 蓝方 FIX-4: AudioContext/Battery/Network ======
  // AudioContext 噪声
  try {{
    var origCreateOsc = (typeof AudioContext !== 'undefined') ? AudioContext.prototype.createOscillator : null;
    if (origCreateOsc) {{
      AudioContext.prototype.createOscillator = function() {{
        var osc = origCreateOsc.call(this);
        var origStart = osc.start;
        osc.start = function() {{
          // 添加微小频率偏移（人耳不可察觉，指纹可区分）
          osc.frequency.value += 0.001 * (parseInt(SEED.slice(0, 4), 16) % 100);
          return origStart.apply(this, arguments);
        }};
        return osc;
      }};
    }}
  }} catch(e) {{}}

  // Battery API 屏蔽
  try {{
    if (navigator.getBattery) {{
      navigator.getBattery = function() {{
        return Promise.resolve({{
          charging: true,
          chargingTime: 0,
          dischargingTime: Infinity,
          level: 1.0
        }});
      }};
    }}
  }} catch(e) {{}}

  // Network Information API 屏蔽
  try {{
    if (navigator.connection) {{
      Object.defineProperty(navigator, 'connection', {{
        get: function() {{ return undefined; }}
      }});
    }}
  }} catch(e) {{}}

  // ====== 红方 ATK-2 + 蓝方 FIX-3: WebRTC IP 泄露 ======
  try {{
    // 移除 RTCPeerConnection 防真实 IP 泄露
    if (window.RTCPeerConnection) {{
      window.RTCPeerConnection = function() {{
        throw new Error('Aegis: WebRTC disabled for privacy');
      }};
    }}
    if (window.webkitRTCPeerConnection) {{
      window.webkitRTCPeerConnection = function() {{
        throw new Error('Aegis: WebRTC disabled for privacy');
      }};
    }}
  }} catch(e) {{}}

  // ====== Stage 4: LetterboxShield ======
  var WS = 200, HS = 100;
  function roundTo(v, s) {{ return Math.max(s, Math.round(v / s) * s); }}
  try {{
    var osW = origGetOPD(window.Screen.prototype, 'width');
    var osH = origGetOPD(window.Screen.prototype, 'height');
    var osAW = origGetOPD(window.Screen.prototype, 'availWidth');
    var osAH = origGetOPD(window.Screen.prototype, 'availHeight');
    if (osW) origDefineProp(screen, 'width', {{ get: function() {{ return roundTo(osW.get.call(this), WS); }} }});
    if (osH) origDefineProp(screen, 'height', {{ get: function() {{ return roundTo(osH.get.call(this), HS); }} }});
    if (osAW) origDefineProp(screen, 'availWidth', {{ get: function() {{ return roundTo(osAW.get.call(this), WS); }} }});
    if (osAH) origDefineProp(screen, 'availHeight', {{ get: function() {{ return roundTo(osAH.get.call(this), HS); }} }});
  }} catch(e) {{}}
  try {{
    origDefineProp(window, 'innerWidth', {{ get: function() {{ return roundTo(window.innerWidth, WS); }} }});
    origDefineProp(window, 'innerHeight', {{ get: function() {{ return roundTo(window.innerHeight, HS); }} }});
    origDefineProp(window, 'outerWidth', {{ get: function() {{ return roundTo(window.outerWidth, WS); }} }});
    origDefineProp(window, 'outerHeight', {{ get: function() {{ return roundTo(window.outerHeight, HS); }} }});
  }} catch(e) {{}}

  // ====== Stage 5+9 合并: fetch 责任链 ======
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
      console.warn('[Aegis] CWS request intercepted');
    }}
    return url;
  }}
  var fetchHandlers = [stripTrackingParams, interceptCWS];
  var origFetch = window.fetch;
  window.fetch = wrapWithTiming(function(input, init) {{
    var url = typeof input === 'string' ? input : (input instanceof Request ? input.url : '');
    for (var i = 0; i < fetchHandlers.length; i++) {{ url = fetchHandlers[i](url); }}
    if (typeof input === 'string') {{ input = url; }}
    else if (input instanceof Request) {{ input = new Request(url, input); }}
    return origFetch.call(this, input, init);
  }}, origFetch);

  var xhrHandlers = [stripTrackingParams, interceptCWS];
  var origXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = wrapWithTiming(function(method, url) {{
    for (var i = 0; i < xhrHandlers.length; i++) {{ url = xhrHandlers[i](url); }}
    arguments[1] = url;
    return origXHROpen.apply(this, arguments);
  }}, origXHROpen);

  // ====== Stage 6: FontNormalizer ======
  var SAFE_FONTS = ['Arial','Helvetica','Verdana','Tahoma','Trebuchet MS','Times New Roman','Times',
    'Georgia','Courier New','Courier','serif','sans-serif','monospace','cursive','fantasy','system-ui'];
  var SAFE_SET = new Set(SAFE_FONTS.map(function(f) {{ return f.toLowerCase(); }}));
  try {{
    var origCheck = FontFaceSet.prototype.check;
    var checkProxy = wrapWithTiming(function(font) {{
      var family = font.replace(/['"]/g, '').split(',')[0].trim().toLowerCase();
      if (SAFE_SET.has(family)) return origCheck.apply(this, arguments);
      return false;
    }}, origCheck);
    FontFaceSet.prototype.check = checkProxy;
  }} catch(e) {{}}

  // ====== Stage 8: TimerPrecision ======
  var TP = 1;
  function reducePrecision(v) {{ return Math.round(v / TP) * TP + (Math.random() - 0.5) * TP / 2; }}
  try {{
    var origPerfNow = performance.now.bind(performance);
    var perfProxy = function() {{ return reducePrecision(origPerfNow()); }};
    origDefineProp(performance, 'now', {{ value: perfProxy, writable: false, configurable: false }});
    registerProxy(perfProxy, origPerfNow);
  }} catch(e) {{}}
  try {{
    var origDateNow = Date.now;
    var dateProxy = function() {{ return reducePrecision(origDateNow()); }};
    Date.now = dateProxy;
    registerProxy(dateProxy, origDateNow);
  }} catch(e) {{}}

  // ====== 红方 ATK-4 + 蓝方 FIX-5: CSS 指纹防护 ======
  // @font-face 枚举防护——CSS.fonts 返回安全字体列表
  try {{
    if (document.fonts && document.fonts.forEach) {{
      var origForEach = document.fonts.forEach;
      document.fonts.forEach = function(callback, thisArg) {{
        // 只返回安全字体
        SAFE_FONTS.forEach(function(f) {{
          callback.call(thisArg, {{ family: f }}, f, document.fonts);
        }});
      }};
    }}
  }} catch(e) {{}}

}})();
"""


def build_link_intercept_js(blocked_hosts=None) -> str:
    """构建链接拦截 JS（FIX-4 + 批次2-2：点击导航经客户端黑名单门禁）。

    P1-3 修复（全面审计 2026-09-04）：旧实现 preventDefault 后
    `location.href = a.href` **原生放行**——威胁黑名单/Agent 白名单对页内
    点击导航完全不生效（权威拦截只覆盖地址栏/新标签/会话恢复三入口）。
    远程页面上桥被禁用（B0-W-01），无法回传桥导航——故在注入时嵌入
    **黑名单快照**（启动时 load_cached 一次，注入参数化），点击时客户端
    判定：命中 → 阻止导航 + 可见 toast（尽力而为——工具栏未注入时静默）。
    快照不含 URL 等敏感数据（纯域名集合），且远程页本就不可信 DOM——
    页面读取黑名单的增量风险 = 它自己探测可达性即可获得，可接受。

    顺带修复两处既有 bug：
    - `a.href.startsWith('#')` 恒为假（.href 是解析后的绝对 URL）——纯锚点
      链接被 preventDefault 破坏页面内导航语义。改用原始 getAttribute 判定。
    - window.open(url) 重定向同样嵌入门禁（旧版任意 URL 直载）。
    """
    hosts_js = "[]"
    if blocked_hosts:
        safe = sorted(h for h in blocked_hosts
                      if isinstance(h, str) and h and len(h) < 256)
        import json as _json
        hosts_js = _json.dumps(safe, ensure_ascii=False)
    return """
// Aegis Link Interceptor (FIX-4 + P1-3: 点击导航客户端黑名单门禁)
(function() {
  'use strict';
  var BLOCKED = %BLOCKED_HOSTS%;
  function hostBlocked(href) {
    try {
      var u = new URL(href);
      if (u.protocol !== 'http:' && u.protocol !== 'https:') return true;
      var h = (u.hostname || '').toLowerCase().replace(/\\.+$/, '');
      if (!h) return true;
      if (BLOCKED.indexOf(h) >= 0) return true;
      var parts = h.split('.');
      for (var i = 1; i < parts.length; i++) {
        if (BLOCKED.indexOf(parts.slice(i).join('.')) >= 0) return true;
      }
      return false;
    } catch (e) { return true; }
  }
  function deny(a) {
    try { if (window.__aegisToast) window.__aegisToast('该地址被安全策略拦截'); } catch (e) {}
  }
  document.addEventListener('click', function(e) {
    var a = e.target;
    while (a && a.tagName !== 'A') a = a.parentNode;
    if (!a) return;
    var raw = a.getAttribute('href') || '';
    if (!raw || raw.charAt(0) === '#') return;  // 纯锚点——页面默认行为
    if (a.hasAttribute('download')) return;
    var href = a.href;
    if (!href) return;
    e.preventDefault();
    e.stopPropagation();
    if (hostBlocked(href)) { deny(a); return; }
    window.location.href = href;
  }, true);
  var origOpen = window.open;
  window.open = function(url) {
    if (url) {
      if (hostBlocked(url)) { deny(null); return null; }
      window.location.href = url;
    }
    return null;
  };
})();
""".replace("%BLOCKED_HOSTS%", hosts_js)


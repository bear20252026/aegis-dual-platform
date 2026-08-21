"""fingerprint_pipeline.py —— 指纹防护 9 阶段管道化注入（单文件单职责）。

与 Rust policy-core 的 fingerprint_pipeline 和 Android SecureWebViewFactory.kt
的 FINGERPRINT_SHIELD_JS 完全对齐——三端一致的 9 阶段防护管线。

每阶段独立 IIFE，互不干扰——可单独禁用/启用。
原始版权声明保留：playwright-afp(MIT)/Brave(MPL-2.0)/Mullvad(MPL-2.0)/Helium(GPL-3.0)
"""

import secrets


def generate_session_seed() -> str:
    """生成 32 字节加密随机种子的 hex 表示。"""
    return secrets.token_hex(32)


def build_fingerprint_pipeline_js(session_seed: str) -> str:
    """构建 9 阶段指纹防护管道 JS 注入脚本。

    Args:
        session_seed: 32 字节 hex 种子（由 generate_session_seed() 生成）

    Returns:
        完整的 JS 注入脚本（9 阶段 IIFE）
    """
    return f"""
// === Stage 1: ToStringGuard（参照 playwright-afp MIT）===
(function() {{
  var proxyMap = new WeakMap();
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {{
    if (proxyMap.has(this)) return origToString.call(proxyMap.get(this));
    return origToString.call(this);
  }};
  Object.defineProperty(window, '__AEGIS_REGISTER_PROXY', {{
    value: function(proxy, original) {{ proxyMap.set(proxy, original); }},
    writable: false, configurable: false
  }});
}})();

// === Stage 2: PerSiteSeed（参照 Brave Browser MPL-2.0）===
(function() {{
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
  var siteSeed = deriveSeed('{session_seed}', getETLD1(location.hostname));
  Object.defineProperty(window, '__AEGIS_SITE_SEED', {{ value: siteSeed, writable: false, configurable: false }});
}})();

// === Stage 3: Canvas/WebGL/Audio 噪声 ===
(function() {{
  var SEED = '{session_seed}';
  var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {{
    var ctx = this.getContext('2d');
    if (ctx) {{
      var imageData = ctx.getImageData(0, 0, this.width, this.height);
      var seed = parseInt(SEED.slice(0, 8), 16);
      for (var i = 0; i < imageData.data.length; i += 4) {{ imageData.data[i] += (seed + i) % 2 === 0 ? 1 : -1; }}
      ctx.putImageData(imageData, 0, 0);
    }}
    return origToDataURL.apply(this, arguments);
  }};
}})();
(function() {{
  var origGetParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {{
    if (p === 37446) return 'ANGLE (Aegis)';
    if (p === 37445) return 'Aegis Privacy';
    return origGetParameter.call(this, p);
  }};
}})();
(function() {{
  var seed = parseInt('{session_seed}'.slice(8, 16), 16);
  Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: function() {{ return 2 + (seed % 7); }} }});
}})();

// === Stage 4: LetterboxShield（参照 Mullvad/Tor Browser MPL-2.0）===
(function() {{
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
}})();

// === Stage 5: QueryStripper（参照 LibreWolf/Brave MPL-2.0）===
(function() {{
  var TP = ['__hsfp','__hssc','__hstc','__s','_hsenc','_openstat','dclid','fbclid','gbraid',
    'gclid','hsCtaTracking','igshid','mc_eid','ml_subscriber','ml_subscriber_hash','msclkid',
    'oft_c','oft_ck','oft_d','oft_id','oft_ids','oft_k','oft_lk','oft_sk','oly_anon_id',
    'oly_enc_id','rb_clickid','s_cid','twclid','vero_conv','vero_id','wickedid','yclid','wbraid'];
  function strip(url) {{
    try {{ var u = new URL(url); var c = false;
      TP.forEach(function(p) {{ if (u.searchParams.has(p)) {{ u.searchParams.delete(p); c = true; }} }});
      return c ? u.toString() : url;
    }} catch(e) {{ return url; }}
  }}
  var origFetch = window.fetch;
  window.fetch = function(input, init) {{
    if (typeof input === 'string') input = strip(input);
    else if (input instanceof Request) input = new Request(strip(input.url), input);
    return origFetch.call(this, input, init);
  }};
  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {{ arguments[1] = strip(url); return origOpen.apply(this, arguments); }};
}})();

// === Stage 6: FontNormalizer（参照 Mullvad Browser MPL-2.0）===
(function() {{
  var SAFE = ['Arial','Helvetica','Verdana','Tahoma','Trebuchet MS','Times New Roman','Times',
    'Georgia','Courier New','Courier','serif','sans-serif','monospace','cursive','fantasy','system-ui'];
  var SAFE_SET = new Set(SAFE.map(function(f) {{ return f.toLowerCase(); }}));
  try {{
    var origCheck = FontFaceSet.prototype.check;
    FontFaceSet.prototype.check = function(font) {{
      var family = font.replace(/['"]/g, '').split(',')[0].trim().toLowerCase();
      if (SAFE_SET.has(family)) return origCheck.apply(this, arguments);
      return false;
    }};
  }} catch(e) {{}}
}})();

// === Stage 7: WebGLSpoof 参数固定（参照 playwright-afp MIT）===
(function() {{
  var VENDOR = 'Google Inc. (Intel)';
  var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
  function patch(proto) {{
    var orig = proto.getParameter;
    proto.getParameter = function(p) {{
      if (p === 0x9245 || p === 0x1F00) return VENDOR;
      if (p === 0x9246 || p === 0x1F01) return RENDERER;
      if (p === 0x0D33) return 16384;
      if (p === 0x0D3A) return new Float32Array([16384, 16384]);
      if (p === 0x84E8) return 16384;
      return orig.call(this, p);
    }};
  }}
  try {{ patch(WebGLRenderingContext.prototype); }} catch(e) {{}}
  try {{ patch(WebGL2RenderingContext.prototype); }} catch(e) {{}}
}})();

// === Stage 8: TimerPrecision（参照 Mullvad Browser MPL-2.0）===
(function() {{
  var P = 1;
  function reduce(v) {{ return Math.round(v / P) * P + (Math.random() - 0.5) * P / 2; }}
  try {{ var o = performance.now.bind(performance); Object.defineProperty(performance, 'now', {{ value: function() {{ return reduce(o()); }}, writable: false, configurable: false }}); }} catch(e) {{}}
  try {{ var d = Date.now; Date.now = function() {{ return reduce(d()); }}; }} catch(e) {{}}
}})();

// === Stage 9: ExtProxy 匿名扩展代理（参照 Helium GPL-3.0）===
(function() {{
  var CWS_DL = /clients2\\.google\\.com\\/service\\/update2\\/crx/i;
  var CWS_UP = /clients2\\.google\\.com\\/service\\/update2\\/json/i;
  function shouldIntercept(url) {{ return CWS_DL.test(url) || CWS_UP.test(url); }}
  try {{
    var origFetch = window.fetch;
    window.fetch = function(input, init) {{
      var url = typeof input === 'string' ? input : (input instanceof Request ? input.url : '');
      if (shouldIntercept(url)) {{ console.warn('[Aegis] CWS request intercepted (no proxy configured)'); }}
      return origFetch.call(this, input, init);
    }};
  }} catch(e) {{}}
}})();
"""

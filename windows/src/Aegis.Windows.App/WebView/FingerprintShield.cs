namespace Aegis.Windows.WebView;

using System;
using System.Security.Cryptography;

/// <summary>指纹防护全量管道（M3——legacy/windows-pywebview/app/
/// fingerprint_pipeline.py 红蓝对抗加固版的原生移植）。每标签会话生成
/// 32 字节加密随机种子；防护 + 反检测在单一闭包内，页面脚本无法绕过
/// （AddScriptToExecuteOnDocumentCreated 文档创建前注入）。
/// 对 Python 版的修正：canvas 噪声仅在离屏副本上扰动读路径——绝不
/// putImageData 写回可见画布（修 Python「污染画布本体」缺陷）。
/// 分片：站点框定素材（公共后缀清单 + 顶层 host 函数）见 FingerprintShield.Seed.cs。</summary>
public static partial class FingerprintShield
{
    /// <summary>生成会话种子（32 字节 → 64 位小写 hex——与 Python
    /// generate_session_seed 的 secrets.token_hex(32) 同构）。</summary>
    public static string NewSessionSeed() =>
        RandomNumberGenerator.GetHexString(64).ToLowerInvariant();

    /// <summary>构建管道注入脚本（种子参数化——同一种子输出逐字节一致，
    /// 便于单测锁定；种子只进 JS 常量，不落盘不外传）。
    /// CS-184：入口校验 fail-closed——种子必须为 64 位小写十六进制
    /// （NewSessionSeed 契约），非法输入抛出而非直插 JS 单引号常量
    /// （注入面：恶意种子可破坏脚本闭包逃逸执行）。</summary>
    public static string BuildScript(string sessionSeed)
    {
        if (sessionSeed is null || sessionSeed.Length != 64 || !IsLowerHex(sessionSeed))
            throw new ArgumentException("会话种子必须为 64 位小写十六进制字符", nameof(sessionSeed));
        return BuildScriptCore(sessionSeed);
    }

    private static bool IsLowerHex(string value)
    {
        foreach (var ch in value)
        {
            var isHex = (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
            if (!isHex)
                return false;
        }
        return true;
    }

    private static string BuildScriptCore(string sessionSeed) =>
        $$"""
        // Aegis Fingerprint Pipeline v3 (Red/Blue Hardened) — C# native port
        (function() {
          'use strict';
          var SEED = '{{sessionSeed}}';
          var proxyMap = new WeakMap();
          var origMap = new WeakMap();

          function registerProxy(proxy, original) {
            proxyMap.set(proxy, original);
            origMap.set(original, proxy);
          }

          // ====== 红方 ATK-1 + 蓝方 FIX-1/2: 原型链检测防护 ======
          var origGetOPD = Object.getOwnPropertyDescriptor;
          var origGetOPN = Object.getOwnPropertyNames;
          var origDefineProp = Object.defineProperty;
          Object.getOwnPropertyDescriptor = function(obj, prop) {
            var desc = origGetOPD.call(Object, obj, prop);
            if (desc && desc.value && proxyMap.has(desc.value)) {
              desc.value = proxyMap.get(desc.value);
            }
            return desc;
          };
          Object.getOwnPropertyNames = function(obj) {
            return origGetOPN.call(Object, obj);
          };

          // ====== Stage 1: ToStringGuard（FIX-5: 闭包封装）======
          var origToString = Function.prototype.toString;
          Function.prototype.toString = function() {
            if (proxyMap.has(this)) return origToString.call(proxyMap.get(this));
            return origToString.call(this);
          };
          registerProxy(Function.prototype.toString, origToString);
          var origToLocale = Function.prototype.toLocaleString;
          Function.prototype.toLocaleString = function() {
            if (proxyMap.has(this)) return origToLocale.call(proxyMap.get(this));
            return origToLocale.call(this);
          };
          registerProxy(Function.prototype.toLocaleString, origToLocale);

          // ====== Stage 2: PerSiteSeed ======
          // CS-381（2026-10-02 审计）：getETLD1 引入公共后缀清单——此前简单取
          // 后两标签，bbc.co.uk 与 shop.co.uk 同得 "co.uk" 种子（跨站噪声可关联
          // ——Rust/Android 侧同孪生已修）；命中清单取后 3 标签（真 eTLD+1）。
          // R7-CS2-10：表体单源化到 FingerprintShield.PublicSuffixes（对账门禁
          // contracts/codegen/verify_seed_framing_parity.py——三端手抄不同表时，同一用户在
          // 不同端拿到不同 eTLD+1，跨站关联面从侧门回来）。
          var PUBLIC_SUFFIXES = {{PublicSuffixTableJs}};
          // R7-CS1-05≡R7-CS2-01：种子必须按**顶层站**框定（Brave 原文：第三方帧
          // 与脚本共享顶层 eTLD+1 的种子）——按本帧 host 派生时，同一跟踪帧在
          // 所有宿主站点产出同一种子，加噪画布哈希本身即跨站持久标识符。
          {{TopLevelHostJs}}
          function getETLD1(h) {
            var p = h.toLowerCase().split('.');
            if (p.length < 2) return h;
            var last2 = p.slice(-2).join('.');
            // bbc.co.uk → bbc.co.uk（后 3）；shop.co.uk → shop.co.uk——两站种子不同
            if (p.length > 2 && PUBLIC_SUFFIXES[last2]) return p.slice(-3).join('.');
            return last2;
          }
          function deriveSeed(hex, domain) {
            var r = '';
            for (var i = 0; i < 16; i++) {
              var acc = parseInt(hex.slice((i % 32) * 2, (i % 32) * 2 + 2), 16);
              for (var j = 0; j < domain.length; j++) { acc = (Math.imul(acc, 31) + domain.charCodeAt(j) + j) | 0; acc ^= (acc >>> 16); }
              r += ('0' + (acc & 0xFF).toString(16)).slice(-2);
            }
            return r;
          }
          var siteSeed = deriveSeed(SEED, getETLD1(aegisTopLevelHostname()));

          // ====== Stage 3+7 合并: Canvas/WebGL/Audio（canvas 离屏副本扰动——
          // 修 Python putImageData 污染可见画布缺陷）======
          // CS-335（2026-10-01 审计·P1）：删除 getContext('2d') 门禁——WebGL
          // 画布取 2d 上下文得 null 即无噪声回退，且无上下文画布被永久锁 2d。
          // 改为离屏副本 drawImage 取像素（对 2d/WebGL 画布同路径生效），
          // 绝不触碰原画布上下文。
          // CS-336（2026-10-01 审计）：噪声种子取 per-site 的 siteSeed（加载时
          // 缓存一次）——此前用会话级 SEED，同用户跨站噪声相同可被跨站关联。
          // CS-380（2026-10-02 审计）：噪声出口补齐 toBlob 与
          // OffscreenCanvas.convertToBlob（对齐 Rust shield.rs RS-206/RS-082
          // 覆盖面）——此前只包裹 toDataURL，另两出口原样读出无噪声。
          // R8-CS-SEC-04（第八轮审计 2026-10-04）取代 CS-379 的 mulberry32：
          // ① 公式与 Rust shield.rs / Android WebViewHardening 收敛为同一条
          //   （murmur3 fmix32 终混 + R/G/B 取 bit0/bit8/bit16 三个互不相交位段）——
          //   三端各持一种噪声算法本身就是指纹差异面，也是三端漂移的来源；
          // ② 每像素新建一个 mulberry32 闭包再调三次是纯浪费（8K×8K 画布即
          //   6.7×10^7 次闭包分配），整数混合免去分配；
          // ③ 扰动不再 `& 0xff` 回绕——0 变 254、255 变 1，既留视觉伪影又给页面
          //   「一行取模即检出防护」的判据；改边界取离岸方向。
          function aegisNoiseMix(seed, px) {
            var m = (seed ^ px) >>> 0;
            m = Math.imul(m ^ (m >>> 16), 0x85ebca6b) >>> 0;
            m = Math.imul(m ^ (m >>> 13), 0xc2b2ae35) >>> 0;
            return (m ^ (m >>> 16)) >>> 0;
          }
          function aegisNudge(current, up) {
            if (current === 0) return 1;
            if (current === 255) return 254;
            return up ? current + 1 : current - 1;
          }
          // R8-CS-SEC-04：像素上限——超限画布直接走原实现（孪生 Android
          // AD-270 同口径）。8K×8K 的离屏副本 + getImageData 是页面可低成本
          // 触发的渲染进程冻结面，本端此前无守卫。
          var AEGIS_MAX_NOISE_PIXELS = 4096 * 4096;
          function buildNoisedCopy(source) {
            if (!source.width || !source.height) return null;
            if (source.width * source.height > AEGIS_MAX_NOISE_PIXELS) return null;
            var tmp, tmpCtx;
            if (typeof document !== 'undefined') {
              tmp = document.createElement('canvas');
              tmp.width = source.width; tmp.height = source.height;
              tmpCtx = tmp.getContext('2d');
            } else if (typeof OffscreenCanvas !== 'undefined') {
              // Worker 语境无 DOM——离屏画布直接做噪声副本
              tmp = new OffscreenCanvas(source.width, source.height);
              tmpCtx = tmp.getContext('2d');
            } else {
              return null;
            }
            tmpCtx.drawImage(source, 0, 0);  // 离屏副本取像素——WebGL 画布同路径
            var imageData = tmpCtx.getImageData(0, 0, source.width, source.height);
            var seed = parseInt(siteSeed.slice(0, 8), 16);
            for (var px = 0, i = 0; i < imageData.data.length; px++, i += 4) {
              var m = aegisNoiseMix(seed, px);
              imageData.data[i] = aegisNudge(imageData.data[i], (m & 1) !== 0);
              imageData.data[i + 1] = aegisNudge(imageData.data[i + 1], ((m >>> 8) & 1) !== 0);
              imageData.data[i + 2] = aegisNudge(imageData.data[i + 2], ((m >>> 16) & 1) !== 0);
            }
            tmpCtx.putImageData(imageData, 0, 0);
            return tmp;
          }
          var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
          var canvasProxy = function() {
            try {
              var tmp = buildNoisedCopy(this);
              if (tmp) return origToDataURL.apply(tmp, arguments);
            } catch (e) { /* tainted canvas——跳过扰动走原路径 */ }
            return origToDataURL.apply(this, arguments);
          };
          registerProxy(canvasProxy, origToDataURL);
          HTMLCanvasElement.prototype.toDataURL = canvasProxy;
          // CS-380：toBlob 出口同款噪声（返回值无关——噪声发生在回调读出的
          // blob 内容上，代理只需让原方法消费噪声副本）
          var origToBlob = HTMLCanvasElement.prototype.toBlob;
          var toBlobProxy = function() {
            try {
              var tmp = buildNoisedCopy(this);
              if (tmp) return origToBlob.apply(tmp, arguments);
            } catch (e) { /* tainted canvas——跳过扰动走原路径 */ }
            return origToBlob.apply(this, arguments);
          };
          registerProxy(toBlobProxy, origToBlob);
          HTMLCanvasElement.prototype.toBlob = toBlobProxy;
          // CS-380：OffscreenCanvas.convertToBlob 出口（Worker 无 DOM——
          // buildNoisedCopy 的 OffscreenCanvas 分支覆盖）
          try {
            if (typeof OffscreenCanvas !== 'undefined' && OffscreenCanvas.prototype.convertToBlob) {
              var origConvertToBlob = OffscreenCanvas.prototype.convertToBlob;
              var convertToBlobProxy = function() {
                try {
                  var tmp = buildNoisedCopy(this);
                  if (tmp) {
                    if (!(tmp instanceof OffscreenCanvas)) {
                      // 窗口语境（document 可用）产的是 DOM 画布——转投离屏
                      var off = new OffscreenCanvas(tmp.width, tmp.height);
                      off.getContext('2d').drawImage(tmp, 0, 0);
                      tmp = off;
                    }
                    return origConvertToBlob.apply(tmp, arguments);
                  }
                } catch (e) { /* tainted canvas——跳过扰动走原路径 */ }
                return origConvertToBlob.apply(this, arguments);
              };
              registerProxy(convertToBlobProxy, origConvertToBlob);
              OffscreenCanvas.prototype.convertToBlob = convertToBlobProxy;
            }
          } catch (e) {}

          // WebGL getParameter（单一代理——WebGLSpoof）
          var VENDOR = 'Google Inc. (Intel)';
          var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
          var origGetParam = WebGLRenderingContext.prototype.getParameter;
          var webglProxy = function(p) {
            if (p === 37446 || p === 0x9246 || p === 0x1F01) return RENDERER;
            if (p === 37445 || p === 0x9245 || p === 0x1F00) return VENDOR;
            if (p === 0x0D33) return 16384;
            if (p === 0x0D3A) return new Int32Array([16384, 16384]); // 规范要求 Int32Array——Float32 可被类型检测识破
            if (p === 0x84E8) return 16384;
            return origGetParam.call(this, p);
          };
          registerProxy(webglProxy, origGetParam);
          WebGLRenderingContext.prototype.getParameter = webglProxy;
          try {
            var origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
            var webgl2Proxy = function(p) {
              if (p === 37446 || p === 0x9246 || p === 0x1F01) return RENDERER;
              if (p === 37445 || p === 0x9245 || p === 0x1F00) return VENDOR;
              if (p === 0x0D33) return 16384;
              if (p === 0x0D3A) return new Int32Array([16384, 16384]);
              if (p === 0x84E8) return 16384;
              return origGetParam2.call(this, p);
            };
            registerProxy(webgl2Proxy, origGetParam2);
            WebGL2RenderingContext.prototype.getParameter = webgl2Proxy;
          } catch(e) {}

          // hardwareConcurrency（会话内稳定扰动）
          var hwSeed = parseInt(SEED.slice(8, 16), 16);
          try {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
              get: function() { return 2 + (hwSeed % 7); }
            });
          } catch(e) {}

          // ====== 红方 ATK-3 + 蓝方 FIX-4: AudioContext/Battery/Network ======
          try {
            var origCreateOsc = (typeof AudioContext !== 'undefined') ? AudioContext.prototype.createOscillator : null;
            if (origCreateOsc) {
              AudioContext.prototype.createOscillator = function() {
                var osc = origCreateOsc.call(this);
                var origStart = osc.start;
                osc.start = function() {
                  osc.frequency.value += 0.001 * (parseInt(SEED.slice(0, 4), 16) % 100);
                  return origStart.apply(this, arguments);
                };
                return osc;
              };
            }
          } catch(e) {}
          try {
            if (navigator.getBattery) {
              navigator.getBattery = function() {
                return Promise.resolve({ charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1.0 });
              };
            }
          } catch(e) {}
          try {
            if (navigator.connection) {
              Object.defineProperty(navigator, 'connection', { get: function() { return undefined; } });
            }
          } catch(e) {}

          // ====== 红方 ATK-2 + 蓝方 FIX-3: WebRTC IP 泄露 ======
          try {
            if (window.RTCPeerConnection) {
              window.RTCPeerConnection = function() { throw new Error('Aegis: WebRTC disabled for privacy'); };
            }
            if (window.webkitRTCPeerConnection) {
              window.webkitRTCPeerConnection = function() { throw new Error('Aegis: WebRTC disabled for privacy'); };
            }
          } catch(e) {}

          // ====== Stage 4: LetterboxShield ======
          var WS = 200, HS = 100;
          function roundTo(v, s) { return Math.max(s, Math.round(v / s) * s); }
          try {
            var osW = origGetOPD.call(Object, window.Screen.prototype, 'width');
            var osH = origGetOPD.call(Object, window.Screen.prototype, 'height');
            var osAW = origGetOPD.call(Object, window.Screen.prototype, 'availWidth');
            var osAH = origGetOPD.call(Object, window.Screen.prototype, 'availHeight');
            if (osW) origDefineProp(screen, 'width', { get: function() { return roundTo(osW.get.call(this), WS); } });
            if (osH) origDefineProp(screen, 'height', { get: function() { return roundTo(osH.get.call(this), HS); } });
            if (osAW) origDefineProp(screen, 'availWidth', { get: function() { return roundTo(osAW.get.call(this), WS); } });
            if (osAH) origDefineProp(screen, 'availHeight', { get: function() { return roundTo(osAH.get.call(this), HS); } });
          } catch(e) {}
          try {
            var oIW = origGetOPD.call(Object, window, 'innerWidth');
            var oIH = origGetOPD.call(Object, window, 'innerHeight');
            var oOW = origGetOPD.call(Object, window, 'outerWidth');
            var oOH = origGetOPD.call(Object, window, 'outerHeight');
            // 先捕获原 getter 再覆盖——getter 内再读同名属性即无限自递归栈溢出
            if (oIW && oIW.get) origDefineProp(window, 'innerWidth', { get: function() { return roundTo(oIW.get.call(this), WS); } });
            if (oIH && oIH.get) origDefineProp(window, 'innerHeight', { get: function() { return roundTo(oIH.get.call(this), HS); } });
            if (oOW && oOW.get) origDefineProp(window, 'outerWidth', { get: function() { return roundTo(oOW.get.call(this), WS); } });
            if (oOH && oOH.get) origDefineProp(window, 'outerHeight', { get: function() { return roundTo(oOH.get.call(this), HS); } });
          } catch(e) {}

          // ====== Stage 5+9 合并: fetch/XHR 责任链 ======
          var TRACKING_PARAMS = ['__hsfp','__hssc','__hstc','__s','_hsenc','_openstat','dclid','fbclid','gbraid',
            'gclid','hsCtaTracking','igshid','mc_eid','ml_subscriber','ml_subscriber_hash','msclkid',
            'oft_c','oft_ck','oft_d','oft_id','oft_ids','oft_k','oft_lk','oft_sk','oly_anon_id',
            'oly_enc_id','rb_clickid','s_cid','twclid','vero_conv','vero_id','wickedid','yclid','wbraid'];
          // CS-331（2026-09-26 审计）：小写冻结集 IIFE 顶层构建一次——此前
          // stripTrackingParams 每次 fetch/XHR 调用都重建 ~40 键对象（请求热
          // 路径重复分配）
          var TRACKING_LOWER = {};
          TRACKING_PARAMS.forEach(function(p) { TRACKING_LOWER[p.toLowerCase()] = true; });
          function stripTrackingParams(url) {
            try { var u = new URL(url); var c = false;
              var doomed = [];
              u.searchParams.forEach(function(v, k) { if (TRACKING_LOWER[k.toLowerCase()]) doomed.push(k); });
              doomed.forEach(function(k) { u.searchParams.delete(k); c = true; });
              return c ? u.toString() : url;
            } catch(e) { return url; }
          }
          var origFetch = window.fetch;
          window.fetch = function(input, init) {
            var url = typeof input === 'string' ? input : (input instanceof Request ? input.url : '');
            url = stripTrackingParams(url);
            if (typeof input === 'string') { input = url; }
            else if (input instanceof Request) { input = new Request(url, input); }
            return origFetch.call(this, input, init);
          };
          var origXHROpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(method, url) {
            arguments[1] = stripTrackingParams(url);
            return origXHROpen.apply(this, arguments);
          };

          // ====== Stage 6: FontNormalizer（红方 ATK-4 + FIX-5: CSS 指纹）======
          var SAFE_FONTS = ['Arial','Helvetica','Verdana','Tahoma','Trebuchet MS','Times New Roman','Times',
            'Georgia','Courier New','Courier','serif','sans-serif','monospace','cursive','fantasy','system-ui'];
          var SAFE_SET = new Set(SAFE_FONTS.map(function(f) { return f.toLowerCase(); }));
          try {
            var origCheck = FontFaceSet.prototype.check;
            var checkProxy = function(font) {
              var family = font.replace(/['"]/g, '').split(',')[0].trim().toLowerCase();
              if (SAFE_SET.has(family)) return origCheck.apply(this, arguments);
              return false;
            };
            registerProxy(checkProxy, origCheck);
            FontFaceSet.prototype.check = checkProxy;
          } catch(e) {}

          // ====== Stage 8: TimerPrecision ======
          var TP = 1;
          function reducePrecision(v) { return Math.round(v / TP) * TP + (Math.random() - 0.5) * TP / 2; }
          // CS-300（2026-09-26 审计）：Date.now 分支——随机抖动直接套在墙上时钟
          // 上会返回非整数（Number.isInteger(Date.now())===false 一行即识破），
          // 且 epoch 量级抖动毫无隐私收益；四舍五入保持整数毫秒
          function reducePrecisionInteger(v) { return Math.round(reducePrecision(v)); }
          try {
            // performance.now：钳单调非递减——随机抖动可产生时间回退
            //（t2 < t1），单调性破坏本身是指纹探针/行为检测信号
            var lastPerf = -Infinity;
            var origPerfNow = performance.now.bind(performance);
            var perfProxy = function() {
              var v = reducePrecision(origPerfNow());
              if (v < lastPerf) v = lastPerf;
              lastPerf = v;
              return v;
            };
            origDefineProp(performance, 'now', { value: perfProxy, writable: false, configurable: false });
            registerProxy(perfProxy, origPerfNow);
          } catch(e) {}
          try {
            var origDateNow = Date.now;
            var dateProxy = function() { return reducePrecisionInteger(origDateNow()); };
            Date.now = dateProxy;
            registerProxy(dateProxy, origDateNow);
          } catch(e) {}

          // ====== CSS.fonts 枚举防护（只回报安全字体）======
          try {
            if (document.fonts && document.fonts.forEach) {
              document.fonts.forEach = function(callback, thisArg) {
                SAFE_FONTS.forEach(function(f) {
                  callback.call(thisArg, { family: f }, f, document.fonts);
                });
              };
            }
          } catch(e) {}
        })();
        """;
}

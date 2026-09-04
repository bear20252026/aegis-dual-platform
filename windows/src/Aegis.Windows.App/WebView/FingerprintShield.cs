namespace Aegis.Windows.WebView;

using System;
using System.Security.Cryptography;

/// <summary>指纹防护全量管道（M3——legacy/windows-pywebview/app/
/// fingerprint_pipeline.py 红蓝对抗加固版的原生移植）。每标签会话生成
/// 32 字节加密随机种子；防护 + 反检测在单一闭包内，页面脚本无法绕过
/// （AddScriptToExecuteOnDocumentCreated 文档创建前注入）。
/// 对 Python 版的修正：canvas 噪声仅在离屏副本上扰动读路径——绝不
/// putImageData 写回可见画布（修 Python「污染画布本体」缺陷）。</summary>
public static class FingerprintShield
{
    /// <summary>生成会话种子（32 字节 → 64 位小写 hex——与 Python
    /// generate_session_seed 的 secrets.token_hex(32) 同构）。</summary>
    public static string NewSessionSeed() =>
        RandomNumberGenerator.GetHexString(64).ToLowerInvariant();

    /// <summary>构建管道注入脚本（种子参数化——同一种子输出逐字节一致，
    /// 便于单测锁定；种子只进 JS 常量，不落盘不外传）。</summary>
    public static string BuildScript(string sessionSeed) =>
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
          var siteSeed = deriveSeed(SEED, getETLD1(location.hostname));

          // ====== Stage 3+7 合并: Canvas/WebGL/Audio（canvas 离屏副本扰动——
          // 修 Python putImageData 污染可见画布缺陷）======
          var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
          var canvasProxy = function() {
            try {
              var ctx = this.getContext('2d');
              if (ctx && this.width && this.height) {
                var imageData = ctx.getImageData(0, 0, this.width, this.height);
                var seed = parseInt(SEED.slice(0, 8), 16);
                for (var i = 0; i < imageData.data.length; i += 4) {
                  imageData.data[i] = (imageData.data[i] + ((seed + i) % 2 === 0 ? 1 : -1)) & 0xff;
                }
                var tmp = document.createElement('canvas');
                tmp.width = this.width; tmp.height = this.height;
                tmp.getContext('2d').putImageData(imageData, 0, 0);
                return origToDataURL.apply(tmp, arguments);
              }
            } catch (e) { /* tainted canvas——跳过扰动走原路径 */ }
            return origToDataURL.apply(this, arguments);
          };
          registerProxy(canvasProxy, origToDataURL);
          HTMLCanvasElement.prototype.toDataURL = canvasProxy;

          // WebGL getParameter（单一代理——WebGLSpoof）
          var VENDOR = 'Google Inc. (Intel)';
          var RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)';
          var origGetParam = WebGLRenderingContext.prototype.getParameter;
          var webglProxy = function(p) {
            if (p === 37446 || p === 0x9246 || p === 0x1F01) return RENDERER;
            if (p === 37445 || p === 0x9245 || p === 0x1F00) return VENDOR;
            if (p === 0x0D33) return 16384;
            if (p === 0x0D3A) return new Float32Array([16384, 16384]);
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
              if (p === 0x0D3A) return new Float32Array([16384, 16384]);
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
            origDefineProp(window, 'innerWidth', { get: function() { return roundTo(window.innerWidth, WS); } });
            origDefineProp(window, 'innerHeight', { get: function() { return roundTo(window.innerHeight, HS); } });
            origDefineProp(window, 'outerWidth', { get: function() { return roundTo(window.outerWidth, WS); } });
            origDefineProp(window, 'outerHeight', { get: function() { return roundTo(window.outerHeight, HS); } });
          } catch(e) {}

          // ====== Stage 5+9 合并: fetch/XHR 责任链 ======
          var TRACKING_PARAMS = ['__hsfp','__hssc','__hstc','__s','_hsenc','_openstat','dclid','fbclid','gbraid',
            'gclid','hsCtaTracking','igshid','mc_eid','ml_subscriber','ml_subscriber_hash','msclkid',
            'oft_c','oft_ck','oft_d','oft_id','oft_ids','oft_k','oft_lk','oft_sk','oly_anon_id',
            'oly_enc_id','rb_clickid','s_cid','twclid','vero_conv','vero_id','wickedid','yclid','wbraid'];
          function stripTrackingParams(url) {
            try { var u = new URL(url); var c = false;
              TRACKING_PARAMS.forEach(function(p) { if (u.searchParams.has(p)) { u.searchParams.delete(p); c = true; } });
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
          try {
            var origPerfNow = performance.now.bind(performance);
            var perfProxy = function() { return reducePrecision(origPerfNow()); };
            origDefineProp(performance, 'now', { value: perfProxy, writable: false, configurable: false });
            registerProxy(perfProxy, origPerfNow);
          } catch(e) {}
          try {
            var origDateNow = Date.now;
            var dateProxy = function() { return reducePrecision(origDateNow()); };
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

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
            // R9-AD-1（第九轮 2026-10-10）：链式包装传递解析到最底层原生（与 Rust
            // tostring_guard.rs、Android StagesSeed 三处同口径）——被拒登记的最外层
            // 不在表内时，它的 toString 会把我方包装源码吐出去。
            var target = original;
            var hops = 0;
            while (proxyMap.has(target) && hops < 8) { target = proxyMap.get(target); hops = hops + 1; }
            proxyMap.set(proxy, target);
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

          {{CanvasSection}}
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

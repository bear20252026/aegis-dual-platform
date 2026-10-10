namespace Aegis.Windows.WebView;

/// <summary>FingerprintShield 的 canvas/WebGL/Audio 段（第八轮 ⑦ 外迁）。
/// 外迁理由与 Rust 端 <c>shield/canvas.rs</c> 同：<c>FingerprintShield.cs</c> 在
/// 411 行零余量基线上，⑦ 的两个像素直读出口无处可放；且这一段自成一组形状判据
/// （三端共用同一公式、编码路径必须用未包裹的 getImageData），由跨端对账门禁
/// <c>core/rust-policy-core/tests/canvas_read_channels.rs</c> 按这个边界读它。</summary>
public static partial class FingerprintShield
{
    /// <summary>Stage 3+7 的 JS 文本。宿主脚本用 <c>$$$</c> 原始插值在本位置插回来；
    /// 段内不含 C# 插值孔（站点种子 <c>siteSeed</c> 是上游 JS 变量），所以可以整体外迁。</summary>
    private const string CanvasSection = """
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
          // ⑦（第八轮，用户 2026-10-07 定稿）：噪声按**画布绝对像素序号**施加
          // （px = y * 画布宽 + x）——编码出口与直读出口共用它，否则「同一点两次读」
          // 本身就是新的检出面。C#/Android/Rust 三端同公式（R8-RS-01 口径延续）。
          function aegisNoiseRectangle(data, seed, sx, sy, sw, sh, stride) {
            for (var row = 0; row < sh; row++) {
              for (var col = 0; col < sw; col++) {
                var i = (row * sw + col) * 4;
                var m = aegisNoiseMix(seed, (sy + row) * stride + (sx + col));
                data[i] = aegisNudge(data[i], (m & 1) !== 0);
                data[i + 1] = aegisNudge(data[i + 1], ((m >>> 8) & 1) !== 0);
                data[i + 2] = aegisNudge(data[i + 2], ((m >>> 16) & 1) !== 0);
              }
            }
          }
          function aegisCanvasSeed() { return parseInt(siteSeed.slice(0, 8), 16); }
          // R8-CS-SEC-04：像素上限——超限画布直接走原实现（孪生 Android
          // AD-270 同口径）。8K×8K 的离屏副本 + getImageData 是页面可低成本
          // 触发的渲染进程冻结面，本端此前无守卫。
          var AEGIS_MAX_NOISE_PIXELS = 4096 * 4096;

          // ⑦：像素直读出口。此前只包编码三出口，页面 `ctx.getImageData(...)`
          // 直接读到无噪原文，与 toDataURL 逐像素比对即 100% 检出防护存在
          //（R8-RS-03）。**包裹顺序是关键**：先把未包裹的原实现留给编码路径，
          // 否则副本被加噪两次，两条出口就不再逐像素一致（这是本项要消除的东西，
          // 不是要换个位置再造一遍）。取不到画布/超出像素上限时原样返回——
          // 超限画布在编码路径同样不加噪，「两条出口一致」优先于「一律加噪」。
          var AEGIS_RAW_GET_IMAGE_DATA = null;
          var AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA = null;
          function aegisWrapRectRead(owner) {
            if (!owner || typeof owner.getImageData !== 'function') return null;
            var orig = owner.getImageData;
            owner.getImageData = function(sx, sy, sw, sh) {
              try {
                var canvas = this.canvas;
                if (!canvas || sw <= 0 || sh <= 0 || sw * sh > AEGIS_MAX_NOISE_PIXELS) {
                  return orig.apply(this, arguments);
                }
                var imageData = orig.apply(this, arguments);
                aegisNoiseRectangle(imageData.data, aegisCanvasSeed(), sx, sy, sw, sh, canvas.width);
                return imageData;
              } catch (e) { /* tainted canvas 等——跳过扰动走原路径 */ }
              return orig.apply(this, arguments);
            };
            // R9-RS-9：注册尾三端同形——try 包裹 + 真值判定后再调（与 Rust
            // canvas.rs、Android WebViewHardeningCanvas.kt 逐 token 一致；本端注册器是
            // ToStringGuard 闭包内的 registerProxy，不对外发布到 window）。
            try { if (registerProxy) registerProxy(owner.getImageData, orig); } catch (e) {}
            return orig;
          }
          if (typeof CanvasRenderingContext2D !== 'undefined') {
            AEGIS_RAW_GET_IMAGE_DATA = aegisWrapRectRead(CanvasRenderingContext2D.prototype);
          }
          if (typeof OffscreenCanvasRenderingContext2D !== 'undefined') {
            AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA = aegisWrapRectRead(OffscreenCanvasRenderingContext2D.prototype);
          }
          // ⑦：WebGL readPixels（v1/v2）。只对「8 位 RGBA、缓冲长度恰为 w*h*4」
          // 加噪——浮点读回数组与 RGB/ALPHA 的步长不是 4 字节，猜错等于把噪声
          // 打进错误通道。WebGL 的 y 轴自下而上、与 2D 不同坐标系，这里求的是
          // 「不泄漏无噪原文」，不是「与 2D 读回逐像素相同」（两者本就不可比）。
          function aegisWrapReadPixels(owner) {
            if (!owner || typeof owner.readPixels !== 'function') return;
            var orig = owner.readPixels;
            owner.readPixels = function(x, y, width, height, format, type, pixels) {
              try {
                var stride = this.drawingBufferWidth;
                var byteRgba = !!pixels && format === this.RGBA &&
                  pixels.length === width * height * 4;
                if (byteRgba && stride && width > 0 && height > 0 &&
                    width * height <= AEGIS_MAX_NOISE_PIXELS) {
                  orig.apply(this, arguments);
                  aegisNoiseRectangle(pixels, aegisCanvasSeed(), x, y, width, height, stride);
                  return;
                }
              } catch (e) { /* 上下文已退休等——不阻断原读回 */ }
              return orig.apply(this, arguments);
            };
            try { if (registerProxy) registerProxy(owner.readPixels, orig); } catch (e) {}
          }
          if (typeof WebGLRenderingContext !== 'undefined') {
            aegisWrapReadPixels(WebGLRenderingContext.prototype);
          }
          if (typeof WebGL2RenderingContext !== 'undefined') {
            aegisWrapReadPixels(WebGL2RenderingContext.prototype);
          }
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
            // ⑦：必须用**未包裹**的 getImageData——本函数产出的副本随后要被编码
            // 出口消费，若再走一次加噪，直读出口与编码出口就不逐像素相同。
            var rawRead = (typeof OffscreenCanvas !== 'undefined' && tmp instanceof OffscreenCanvas)
              ? (AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA || AEGIS_RAW_GET_IMAGE_DATA)
              : AEGIS_RAW_GET_IMAGE_DATA;
            if (!rawRead) return null;
            var imageData = rawRead.call(tmpCtx, 0, 0, source.width, source.height);
            aegisNoiseRectangle(imageData.data, aegisCanvasSeed(), 0, 0, source.width, source.height, source.width);
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

    """;
}

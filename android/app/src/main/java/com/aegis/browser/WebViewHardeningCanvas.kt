package com.aegis.browser

// Stage 3 的 canvas/WebGL 注入文本（第八轮 ⑦ 自 WebViewHardeningStagesSeed.kt 外迁）。
//
// Seed 文件在 327 行零余量基线上，⑦ 的像素直读段无处可放；而 Stage 1-3 的闭包作用域
// 不能再切一刀（站点种子只活在那一层），所以切的是**文本**：本 object 逐字承载 canvas
// IIFE，宿主在原位置插回 WebViewHardeningCanvas.js，拼接后与拆分前逐字节一致。
// 跨端对账门禁 core/rust-policy-core/tests/canvas_read_channels.rs 按这个边界读三份源码。
internal object WebViewHardeningCanvas {
    internal val js: String = """  (function() {
    // AD-314（2026-10-02 审计）：各包装点补注册调用——AD-297 修好 Symbol 键后，
    // Stage 1 的 ToStringGuard 才真正可达；本阶段三个 canvas 包装同样注册，
    // 防止 toDataURL.toString() 暴露包装源码。
    var __aegisReg = window[Symbol.for('proxy.register.v1')];
    // AD-270（2026-10-01 审计）：尺寸上限——16K×16K 画布的离屏副本 +
    // getImageData 峰值约 1GB（OOM 面）。超阈值直接走原实现降级（该形态
    // 画布本身已极难作为指纹载体，资源安全优先）。
    var MAX_NOISE_PIXELS = 4096 * 4096;
    // AD-311（2026-10-02 审计）：Uint8ClampedArray 在 0/255 边界吸收 ±1 噪声
    //（0-1 → 0、255+1 → 255，边界像素噪声不可见=指纹可分离）。边界像素噪声
    // 取离岸方向（0→+1、255→-1），中间值按噪声位 ±1。
    function aegisNudge(current, noiseBit) {
      if (current === 0) return 1;
      if (current === 255) return 254;
      return noiseBit ? current + 1 : current - 1;
    }
    // R8-RS-01/R8-CS-SEC-04（第八轮审计 2026-10-04）取代 AD-253 口径：三端统一为
    // murmur3 fmix32 终混 + R/G/B 取 bit0/bit8/bit16 三个互不相交位段。
    // AD-253 那版仍偏窄——`(seed ^ Math.imul(px, K)) & 1` 里三枚常数全为奇数，
    // 乘积最低位＝px 最低位，所以噪声位只由像素序号奇偶决定（2 个相位），且三通道
    // 恒等（正是「通道差分即抵消」的形态）。fmix32 把输入每一位都搅进输出，
    // bit0 不再由奇偶决定，通道间取不同位段因而互相独立。Rust shield.rs 与
    // Windows FingerprintShield.cs 用同一公式——三端各持一种算法本身就是指纹差异面。
    // alpha 不动——不破坏合成透明度。三出口共用（AD-298）。
    function aegisNoiseMix(seed, px) {
      var m = (seed ^ px) >>> 0;
      m = Math.imul(m ^ (m >>> 16), 0x85ebca6b) >>> 0;
      m = Math.imul(m ^ (m >>> 13), 0xc2b2ae35) >>> 0;
      return (m ^ (m >>> 16)) >>> 0;
    }
    // ⑦（第八轮，用户 2026-10-07 定稿）：噪声按**画布绝对像素序号**施加
    // （px = y * 画布宽 + x）——编码出口与像素直读出口共用这一处循环，否则
    // 「同一点两次读」本身就是新的检出面。Rust shield/canvas.rs 与
    // Windows FingerprintShield.Canvas.cs 同公式同形状（R8-RS-01 口径延续）。
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
    function applyNoise(imageData, seed) {
      var w = imageData.width;
      aegisNoiseRectangle(imageData.data, seed, 0, 0, w, imageData.height, w);
    }
    // 审计第六轮（2026-10-03）：裸标识符取外层 Stage 2 闭包常量（种子
    // 全局导出已撤销）——种子不外泄，噪声消费点仍在同一闭包作用域内闭环。
    function noiseSeed() { return parseInt(__AEGIS_SITE_SEED.slice(0, 8), 16); }

    // ⑦：像素直读出口。此前只包编码三出口，页面 ctx.getImageData(...) 直接读到
    // 无噪原文，与 toDataURL 逐像素比对即 100% 检出防护存在（R8-RS-03）。
    // **包裹顺序是关键**：先把未包裹的原实现留给编码路径，否则离屏副本被加噪
    // 两次——两条出口就不再逐像素一致。取不到画布/超出尺寸上限时原样返回：
    // 超限画布在编码路径同样不加噪，「两条出口一致」优先于「一律加噪」。
    var AEGIS_RAW_GET_IMAGE_DATA = null;
    var AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA = null;
    function aegisWrapRectRead(owner) {
      if (!owner || typeof owner.getImageData !== 'function') return null;
      var orig = owner.getImageData;
      owner.getImageData = function(sx, sy, sw, sh) {
        try {
          var canvas = this.canvas;
          if (!canvas || sw <= 0 || sh <= 0 || sw * sh > MAX_NOISE_PIXELS) {
            return orig.apply(this, arguments);
          }
          var imageData = orig.apply(this, arguments);
          aegisNoiseRectangle(imageData.data, noiseSeed(), sx, sy, sw, sh, canvas.width);
          return imageData;
        } catch (e) {
          return orig.apply(this, arguments);
        }
      };
      if (__aegisReg) __aegisReg(owner.getImageData, orig);
      return orig;
    }
    if (typeof CanvasRenderingContext2D !== 'undefined') {
      AEGIS_RAW_GET_IMAGE_DATA = aegisWrapRectRead(CanvasRenderingContext2D.prototype);
    }
    if (typeof OffscreenCanvasRenderingContext2D !== 'undefined') {
      AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA = aegisWrapRectRead(OffscreenCanvasRenderingContext2D.prototype);
    }
    // ⑦：WebGL readPixels（v1/v2）。只对「8 位 RGBA、缓冲长度恰为 w*h*4」加噪——
    // 浮点读回与 RGB/ALPHA 等 format 的步长不是 4 字节，猜错等于把噪声打进错误
    // 通道。WebGL 的 y 轴自下而上、与 2D 不同坐标系，这里求的是「不泄漏无噪原文」，
    // 不是「与 2D 读回逐像素相同」（两者本就不可比）。
    function aegisWrapReadPixels(owner) {
      if (!owner || typeof owner.readPixels !== 'function') return;
      var orig = owner.readPixels;
      owner.readPixels = function(x, y, width, height, format, type, pixels) {
        try {
          var stride = this.drawingBufferWidth;
          var byteRgba = !!pixels && format === this.RGBA &&
            pixels.length === width * height * 4;
          if (byteRgba && stride && width > 0 && height > 0 &&
              width * height <= MAX_NOISE_PIXELS) {
            orig.apply(this, arguments);
            aegisNoiseRectangle(pixels, noiseSeed(), x, y, width, height, stride);
            return;
          }
        } catch (e) { /* 上下文已退休等——不阻断原读回 */ }
        return orig.apply(this, arguments);
      };
      if (__aegisReg) __aegisReg(owner.readPixels, orig);
    }
    if (typeof WebGLRenderingContext !== 'undefined') {
      aegisWrapReadPixels(WebGLRenderingContext.prototype);
    }
    if (typeof WebGL2RenderingContext !== 'undefined') {
      aegisWrapReadPixels(WebGL2RenderingContext.prototype);
    }
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
        const imageData = AEGIS_RAW_GET_IMAGE_DATA.call(octx, 0, 0, off.width, off.height);
        applyNoise(imageData, noiseSeed());
        octx.putImageData(imageData, 0, 0);
        return origToDataURL.apply(off, arguments);
      } catch (e) {
        return origToDataURL.apply(this, arguments);
      }
    };
    if (__aegisReg) __aegisReg(HTMLCanvasElement.prototype.toDataURL, origToDataURL);
    // AD-298（2026-10-02 审计）：toBlob 是 canvas 读取的第二通道——此前仅覆盖
    // toDataURL，页面走 toBlob 即拿到无噪声原图。按 Rust shield.rs RS-082 同型
    // 补齐（离屏副本 + 逐像素噪声 + 尺寸上限，口径与 toDataURL 通道一致）。
    var origToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
      try {
        if (this.width * this.height > MAX_NOISE_PIXELS) {
          return origToBlob.call(this, callback, type, quality);
        }
        const off = document.createElement('canvas');
        off.width = this.width;
        off.height = this.height;
        const octx = off.getContext('2d');
        octx.drawImage(this, 0, 0);
        const imageData = AEGIS_RAW_GET_IMAGE_DATA.call(octx, 0, 0, off.width, off.height);
        applyNoise(imageData, noiseSeed());
        octx.putImageData(imageData, 0, 0);
        return origToBlob.call(off, callback, type, quality);
      } catch (e) {
        return origToBlob.call(this, callback, type, quality);
      }
    };
    if (__aegisReg) __aegisReg(HTMLCanvasElement.prototype.toBlob, origToBlob);
    // AD-298：OffscreenCanvas.convertToBlob 是 worker 侧第三通道——同型防护
    //（RS-082；宿主无 OffscreenCanvas 时本包装空转）。
    if (typeof OffscreenCanvas !== 'undefined') {
      const origConvert = OffscreenCanvas.prototype.convertToBlob;
      OffscreenCanvas.prototype.convertToBlob = function(options) {
        try {
          if (this.width * this.height > MAX_NOISE_PIXELS) {
            return origConvert.call(this, options);
          }
          const off = new OffscreenCanvas(this.width, this.height);
          const octx = off.getContext('2d');
          octx.drawImage(this, 0, 0);
          const rawRead = AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA || AEGIS_RAW_GET_IMAGE_DATA;
          if (!rawRead) return origConvert.call(this, options);
          const imageData = rawRead.call(octx, 0, 0, off.width, off.height);
          applyNoise(imageData, noiseSeed());
          octx.putImageData(imageData, 0, 0);
          return origConvert.call(off, options);
        } catch (e) {
          return origConvert.call(this, options);
        }
      };
      if (__aegisReg) __aegisReg(OffscreenCanvas.prototype.convertToBlob, origConvert);
    }
  })();
    """.trimEnd()
}

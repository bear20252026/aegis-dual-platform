//! canvas 噪声段（R8-RS-01 单源公式 + 三个编码出口 + ⑦ 的两个像素直读出口）。
//!
//! 从 `shield.rs` 外迁有两个理由：① `shield.rs` 在 352 行零余量基线上，⑦ 的直读
//! 出口无处可放（本仓 ratchet 只许减不许增）；② 这一段的形状判据自成一组——
//! 「三端共用同一公式」「编码路径必须用未包裹的 getImageData」由跨端对账门禁
//! `tests/canvas_read_channels.rs` 按这个边界读它。
//!
//! 文本仍是 `format!` 模板（JS 花括号按 Rust 惯例双写），`{reg_sym}` 由调用方注入；
//! 段落在整段注入脚本里的位置就是原位置（上游是站点种子函数），不得移动。

/// 生成 canvas 段 JS。`reg_sym` 是 ToStringGuard 的注册符号名（代理登记表键）。
pub(crate) fn canvas_js(reg_sym: &str) -> String {
    format!(
        r#"  // R8-RS-01（第八轮审计 2026-10-04）：噪声混合函数单源——三端（Rust/Android
  // WebViewHardening.aegisNudge·applyNoise / Windows FingerprintShield）共用同一
  // 公式：murmur3 fmix32 终混 + R/G/B 取互不相交的位段（bit0 / bit8 / bit16）。
  // 此前 RS-249 用「字节偏移 x 奇数常数取最低位」的形态，数学上恒退化：三枚常数全为奇数，
  // 乘积最低位＝操作数最低位，而 i+=4 步进使字节偏移恒为偶 ⇒ 每像素每通道的扰动
  // 都等于 `seed & 1`——全图同一 ±1 偏移，有效熵 1 bit，家只需试 2 个候选即可确定
  // 性还原真画布，canvas 哈希仍是可归一的稳定标识符（正是该机制要消除的东西）。
  // fmix32 把输入的每一位都搅进输出，bit0 不再由像素序号奇偶决定，通道间取不同
  // 位段因而互相独立。Android 侧 AD-253 用像素序号（2 个相位）同样偏窄，同批收口。
  function aegisNoiseMix(seed, px) {{
    var m = (seed ^ px) >>> 0;
    m = Math.imul(m ^ (m >>> 16), 0x85ebca6b) >>> 0;
    m = Math.imul(m ^ (m >>> 13), 0xc2b2ae35) >>> 0;
    return (m ^ (m >>> 16)) >>> 0;
  }}
  // 边界不外溢：0 只能升、255 只能降。(x + d) & 0xff 会把黑变 254、白变 1——
  // 既留视觉伪影，又给页面「一行取模即检出防护」的判据（R8-CS-SEC-04 同型修于三端）。
  function aegisNudge(current, up) {{
    if (current === 0) return 1;
    if (current === 255) return 254;
    return up ? current + 1 : current - 1;
  }}
  // R8-RS-01：编码三出口（toDataURL/toBlob/convertToBlob）与 ⑦ 的像素直读出口
  // 共用的单源噪声施加函数。⑦ 起按**画布绝对像素序号**取噪（px = y * 画布宽 + x）：
  // 子矩形读回必须换算回同一序号，否则「同一点两次读」本身就是新的检出面。
  function aegisNoiseRectangle(data, seed, sx, sy, sw, sh, stride) {{
    for (var row = 0; row < sh; row++) {{
      for (var col = 0; col < sw; col++) {{
        var i = (row * sw + col) * 4;
        var m = aegisNoiseMix(seed, (sy + row) * stride + (sx + col));
        data[i] = aegisNudge(data[i], (m & 1) !== 0);
        data[i + 1] = aegisNudge(data[i + 1], ((m >>> 8) & 1) !== 0);
        data[i + 2] = aegisNudge(data[i + 2], ((m >>> 16) & 1) !== 0);
      }}
    }}
  }}
  function aegisApplyCanvasNoise(imageData, seed) {{
    var w = imageData.width;
    aegisNoiseRectangle(imageData.data, seed, 0, 0, w, imageData.height, w);
  }}
  // R8-CS-SEC-04：像素上限——超限画布直接走原实现（16K×16K 的离屏副本 +
  // getImageData 峰值约 1GB，是远程页可低成本触发的标签页冻结面）。
  var AEGIS_MAX_NOISE_PIXELS = 4096 * 4096;
  // ⑦（第八轮，用户 2026-10-07 定稿）：像素直读出口第一类——getImageData
  //（2D 与 OffscreenCanvas 2d 两个原型）。此前只包编码出口，页面
  // `ctx.getImageData(...)` 直接读到无噪原文，与 toDataURL 逐像素比对即 100%
  // 检出防护存在（R8-RS-03）。
  // **包裹顺序是关键**：先把未包裹的原实现留给编码路径，否则离屏副本会被加噪
  // 两次——编码出口与直读出口就不再逐像素一致，那正是本项要消除的东西。
  // 取不到画布或超出像素上限时原样返回：超限画布在编码路径同样不加噪，
  // 「两条出口保持一致」比「一律加噪」更重要。
  var AEGIS_RAW_GET_IMAGE_DATA = null;
  var AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA = null;
  function aegisWrapRectRead(owner) {{
    if (!owner || typeof owner.getImageData !== 'function') return null;
    const orig = owner.getImageData;
    owner.getImageData = function(sx, sy, sw, sh) {{
      try {{
        const canvas = this.canvas;
        if (!canvas || sw <= 0 || sh <= 0 || sw * sh > AEGIS_MAX_NOISE_PIXELS) {{
          return orig.apply(this, arguments);
        }}
        const imageData = orig.apply(this, arguments);
        aegisNoiseRectangle(imageData.data, aegisCanvasSeed(), sx, sy, sw, sh, canvas.width);
        return imageData;
      }} catch (e) {{}}
      return orig.apply(this, arguments);
    }};
    try {{ if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](owner.getImageData, orig); }} catch (e) {{}}
    return orig;
  }}
  if (typeof CanvasRenderingContext2D !== 'undefined') {{
    AEGIS_RAW_GET_IMAGE_DATA = aegisWrapRectRead(CanvasRenderingContext2D.prototype);
  }}
  if (typeof OffscreenCanvasRenderingContext2D !== 'undefined') {{
    AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA = aegisWrapRectRead(OffscreenCanvasRenderingContext2D.prototype);
  }}

  // ⑦：像素直读出口第二类——WebGL readPixels（v1/v2 两个原型）。只对
  // 「8 位 RGBA、缓冲长度恰为 w*h*4」的读回加噪：HALF_FLOAT/FLOAT 读回的是浮点数组，
  // RGB/ALPHA 等 format 的步长不是 4 字节，猜错步长等于把噪声打进错误通道。
  // WebGL 的 y 轴自下而上，与 2D 画布不同坐标系——这里追求的是「不泄漏无噪原文」，
  // 不是「与 2D 读回逐像素相同」（两者本就不可比）。
  function aegisWrapReadPixels(owner) {{
    if (!owner || typeof owner.readPixels !== 'function') return;
    const orig = owner.readPixels;
    owner.readPixels = function(x, y, width, height, format, type, pixels) {{
      try {{
        const stride = this.drawingBufferWidth;
        const byteRgba = !!pixels && format === this.RGBA &&
          pixels.length === width * height * 4;
        if (byteRgba && stride && width > 0 && height > 0 &&
            width * height <= AEGIS_MAX_NOISE_PIXELS) {{
          orig.apply(this, arguments);
          aegisNoiseRectangle(pixels, aegisCanvasSeed(), x, y, width, height, stride);
          return;
        }}
      }} catch (e) {{}}
      return orig.apply(this, arguments);
    }};
    try {{ if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](owner.readPixels, orig); }} catch (e) {{}}
  }}
  if (typeof WebGLRenderingContext !== 'undefined') {{
    aegisWrapReadPixels(WebGLRenderingContext.prototype);
  }}
  if (typeof WebGL2RenderingContext !== 'undefined') {{
    aegisWrapReadPixels(WebGL2RenderingContext.prototype);
  }}

  // Canvas 噪声（每个像素 ±1 随机偏移——视觉不可察觉）
  // RS-025（审计 2026-09-24）：噪声施加在**离屏副本**上——此前就地
  // putImageData 把噪声写回原画布，页面双读（toDataURL 前后各 getImageData
  // 一次）即可检测像素漂移
  // RS-206（2026-09-26 审计）：删除源画布的 getContext('2d')
  // 前置门禁——①画布已持 WebGL 上下文时 getContext('2d') 返回 null，
  // 噪声被整体绕过（WebGL 画布恰是主流指纹向量）；②画布尚无上下文时
  // 该调用会把画布永久锁定为 2d（页面随后 getContext('webgl') 得 null，
  // 渲染被破坏）。drawImage(this) 对任意上下文类型的源画布均可用，
  // 离屏副本自取 2d 上下文即可
  (function() {{
    // RS-292（2026-10-02 审计）：worker 作用域守卫——HTMLCanvasElement 在
    // worker 未定义，裸引用即抛未捕获 ReferenceError（脚本整体中断，后续
    // 阶段全部失效）；注册行 try 包（worker 无 window，对齐 per_site_seed
    // 全 try 口径）
    if (typeof HTMLCanvasElement === 'undefined') return;
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {{
      try {{
        if (this.width * this.height > AEGIS_MAX_NOISE_PIXELS) {{
          return origToDataURL.apply(this, arguments);
        }}
        const off = document.createElement('canvas');
        off.width = this.width;
        off.height = this.height;
        const octx = off.getContext('2d');
        octx.drawImage(this, 0, 0);
        const imageData = AEGIS_RAW_GET_IMAGE_DATA.call(octx, 0, 0, off.width, off.height);
        aegisApplyCanvasNoise(imageData, aegisCanvasSeed());
        octx.putImageData(imageData, 0, 0);
        return origToDataURL.apply(off, arguments);
      }} catch (e) {{}}
      return origToDataURL.apply(this, arguments);
    }};
  try {{ if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](HTMLCanvasElement.prototype.toDataURL, origToDataURL); }} catch (e) {{}}
}})();

// RS-082（审计 2026-09-25）：toBlob 是 canvas 读取的第二通道——仅覆盖
// toDataURL 时页面走 toBlob 拿到无噪声原图。同型离屏副本 + 噪声
//（RS-206/207/215 口径与 toDataURL 通道一致）
(function() {{
  // RS-292：worker 作用域守卫 + 注册行 try 包（同 toDataURL 块口径）
  if (typeof HTMLCanvasElement === 'undefined') return;
  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
    try {{
      if (this.width * this.height > AEGIS_MAX_NOISE_PIXELS) {{
        return origToBlob.call(this, callback, type, quality);
      }}
      const off = document.createElement('canvas');
      off.width = this.width;
      off.height = this.height;
      const octx = off.getContext('2d');
      octx.drawImage(this, 0, 0);
      const imageData = AEGIS_RAW_GET_IMAGE_DATA.call(octx, 0, 0, off.width, off.height);
      aegisApplyCanvasNoise(imageData, aegisCanvasSeed());
      octx.putImageData(imageData, 0, 0);
      return origToBlob.call(off, callback, type, quality);
    }} catch (e) {{}}
    return origToBlob.call(this, callback, type, quality);
  }};
  try {{ if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](HTMLCanvasElement.prototype.toBlob, origToBlob); }} catch (e) {{}}
}})();

// RS-082：OffscreenCanvas.convertToBlob 是 worker 侧第三通道——同型防护
//（RS-206/207/215 口径与 toDataURL 通道一致）
(function() {{
  if (typeof OffscreenCanvas === 'undefined') return;
  const origConvert = OffscreenCanvas.prototype.convertToBlob;
  OffscreenCanvas.prototype.convertToBlob = function(options) {{
    try {{
      if (this.width * this.height > AEGIS_MAX_NOISE_PIXELS) {{
        return origConvert.call(this, options);
      }}
      const off = new OffscreenCanvas(this.width, this.height);
      const octx = off.getContext('2d');
      octx.drawImage(this, 0, 0);
      const rawRead = AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA || AEGIS_RAW_GET_IMAGE_DATA;
      if (!rawRead) return origConvert.call(this, options);
      const imageData = rawRead.call(octx, 0, 0, off.width, off.height);
      aegisApplyCanvasNoise(imageData, aegisCanvasSeed());
      octx.putImageData(imageData, 0, 0);
      return origConvert.call(off, options);
    }} catch (e) {{}}
    return origConvert.call(this, options);
  }};
  try {{ if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](OffscreenCanvas.prototype.convertToBlob, origConvert); }} catch (e) {{}}
}})();
"#,
    )
}

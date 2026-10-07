// Stage 1-3（ToStringGuard / PerSiteSeed / Canvas 噪声 + hardwareConcurrency）的注入文本。
//
// R8-CS-SEC-14（第八轮 2026-10-06）自 WebViewHardening.kt 拆出：那个 object 是本仓最大的
// 存量文件，detekt 的 LargeClass（阈值 600）随第八轮 R8-RS-09 的注册窗口改造越线——按台账
// 该条目既有的建议**净减拆分**而不是加抑制。三段留在这里是因为 Stage 2 的闭包同时是
// Stage 3/3c 的种子作用域（种子只活在这一层，见 AD-269/审计第六轮注记），拆开会破坏作用域。
//
// 拼接顺序即注入顺序：本文件在前、WebViewHardeningStagesShield 在后，两者由
// `WebViewHardening.fingerprintShieldScript` 串成一段脚本——注入语义与拆分前逐字节一致。
package com.aegis.browser

internal object WebViewHardeningStagesSeed {
    @Suppress("LongMethod") // 仅承载版本化脚本文本，不含 Android 业务控制流。
    internal fun script(sessionSeed: String): String =
        """
// AD-269（2026-10-01 审计）：版本标记改 defineProperty——裸赋值产出的数据
// 属性默认可枚举（Object.keys / for-in 一行可枚举）且可 delete；不可枚举 +
// 不可配置后，枚举面不可见且不可删除（writable 同步锁死，防篡改降级探测）。
Object.defineProperty(window, '__AEGIS_PROTECTION_VERSION', {
  value: '1', writable: false, enumerable: false, configurable: false
});
// === Stage 1: ToStringGuard（参照 playwright-afp MIT）===
(function() {
  var proxyMap = new WeakMap();
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {
    if (proxyMap.has(this)) return origToString.call(proxyMap.get(this));
    return origToString.call(this);
  };
  // AD-297（2026-10-02 审计）：注册键改 Symbol.for('proxy.register.v1')——原
  // 具名字符串键 '__AEGIS_REGISTER_PROXY' 与桥守卫（BRIDGE_GUARD_JS）读取的
  // Symbol 键不匹配，桥守卫侧 __aegisReg 恒 undefined、四桥出口注册全部空转
  //（fetch.toString() 一行暴露包装源码）。对齐 Rust ToStringGuard（RS-027）
  // 与本脚本 Stage 3-9 各包装点的注册读取键：Symbol 键按具名字符串探测落空、
  // 不出现在 Object.keys/getOwnPropertyNames 字符串枚举通道。
  // R8-RS-09（第八轮 2026-10-06）：注册接口与 Rust 的 ToStringGuard 对齐。
  // AD-297 版只有裸 set，且 configurable: false ⇒ 既无参数校验（页面可把任意
  // 自己的钩子登记成任一原生函数的替身），也**永不撤销**（不可替换就没有关闭
  // 通道）——比我方 Rust 侧的 RS-252 校验更弱。现在：闭包内窗口标志 + 双函数
  // 校验 + original/proxy 两侧都不得已登记，并在本 blob 末尾同步关窗
  //（页面脚本只可能在 blob 之后执行 ⇒ 伪造映射窗口为零；引用被捕获也无用，
  // 因为失效发生在函数体内部而不是属性替换上）。
  var open = true;
  Object.defineProperty(window, Symbol.for('proxy.register.v1'), {
    value: function(proxy, original) {
      if (!open) return;
      if (typeof proxy !== 'function' || typeof original !== 'function') return;
      if (proxyMap.has(original) || proxyMap.has(proxy)) return;
      proxyMap.set(proxy, original);
    },
    writable: false, configurable: false
  });
  // 撤销键：幂等且不可替换——页面能用它做的只有**提前**关窗（fail-closed 方向）。
  Object.defineProperty(window, Symbol.for('proxy.register.close.v1'), {
    value: function() { open = false; },
    writable: false, configurable: false
  });
})();

// === Stage 2: PerSiteSeed（参照 Brave Browser MPL-2.0）===
// 审计第六轮（2026-10-03）：本闭包除派生种子外，还内嵌 Stage 3（canvas 噪声）
// 与 Stage 3c（hardwareConcurrency）两个种子消费点——参照实现
// per_site_seed.rs:24-28 的封装口径（种子只活在这一层作用域里）。
(function() {
  // AD-107（审计 2026-09-23 清单·A6 批）：getETLD1 迷你公共后缀表——原实现
  // 一律取最后两段，把 a.co.uk 与 b.co.uk 推导出不同 site seed（eTLD+1 应同为
  // co.uk 域，同站不同源实体各持指纹种子既不隐私正确也不一致）。未命中回落两段式。
  // R7-CS2-10（第七轮 2026-10-04）：表体与 contracts/policy/public-suffix-list.txt
  // 逐项对账（contracts/codegen/verify_seed_framing_parity.py）——三端曾各持 51/54/31 条手抄表，
  // user.github.io 在缺托管域条目的一侧被折成 github.io，该用户全部 GitHub Pages
  // 站点共享一种子；AD-329 补齐的两段后缀（co.il/org.il/com.ua/…）同表保留。
  var PUBLIC_SUFFIXES = ['ac.cn','ac.jp','ac.th','ac.uk','appspot.com','azurewebsites.net','blogspot.com','cloudfront.net','co.id',
    'co.il','co.in','co.jp','co.kr','co.nz','co.th','co.uk','co.za','com.ar',
    'com.au','com.br','com.cn','com.co','com.ec','com.gr','com.hk','com.mx','com.my',
    'com.pe','com.ph','com.pk','com.pl','com.pt','com.py','com.ro','com.ru','com.sa',
    'com.sg','com.tr','com.tw','com.ua','com.uy','com.ve','com.vn','edu.au','edu.cn',
    'edu.hk','github.io','gitlab.io','go.id','go.jp','gob.mx','gov.au','gov.cn','gov.uk',
    'herokuapp.com','ne.jp','ne.kr','net.au','net.cn','net.in','net.nz','net.sg','net.uk',
    'netlify.app','or.jp','or.kr','or.th','org.au','org.cn','org.hk','org.il','org.in',
    'org.nz','org.ru','org.sg','org.tw','org.uk','pages.dev','vercel.app'];
  function isPublicSuffix(tail) { return PUBLIC_SUFFIXES.indexOf(tail) >= 0; }
  function getETLD1(h) {
    var p = h.split('.');
    if (p.length <= 2) return h;
    var tail2 = p.slice(-2).join('.');
    if (isPublicSuffix(tail2)) {
      // 公共后缀占两段 → eTLD+1 取三段；三段仍不足以构成注册域时退回原 host
      return p.length >= 3 ? p.slice(-3).join('.') : h;
    }
    return tail2;
  }
  // AD-005（审计 2026-09-23 清单·真机批次）：自制 acc*31 混合 → 同步 SHA-256。
  // 构造与 Rust per_site_seed（RS-025/P25）对齐：
  //   SHA-256(hexDecode(sessionSeed) || 'aegis:per-site-seed:v2:' || domain)[0..16] hex
  // 自制混合的域间密钥分离无密码学背书（单域种子可逆推会话种子结构）。
  // document-start 一次性注入架构（addDocumentStartJavaScript 无 per-page
  // 入口）决定派生必须留在 JS 侧——台账「Kotlin 侧派生」方案在此约束下
  // 落地为「JS 内嵌同步 SHA-256、构造对齐 Rust」；已知答案由模拟器
  // instrumented 测试对 Kotlin MessageDigest 逐字节验证（AD-067 冒烟集）。
  function hexToBytes(hex) {
    var out = new Uint8Array(hex.length >> 1);
    for (var i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
    return out;
  }
  function sha256Raw(msg) {
    var K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
             0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
             0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
             0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
             0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
             0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
             0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
             0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    var H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
    var len = msg.length;
    var padded = new Uint8Array((((len + 8) >> 6) + 1) << 6);
    padded.set(msg); padded[len] = 0x80;
    var dv = new DataView(padded.buffer);
    dv.setUint32(padded.length - 8, Math.floor(len / 0x20000000));
    dv.setUint32(padded.length - 4, (len << 3) >>> 0);
    var w = new Array(64);
    for (var off = 0; off < padded.length; off += 64) {
      for (var i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
      for (var i = 16; i < 64; i++) {
        var s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >>> 3);
        var s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >>> 10);
        w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
      }
      var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
      for (var i = 0; i < 64; i++) {
        var S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
        var S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
        var mj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + mj) >>> 0;
        h=g; g=f; f=e; e=(d + t1) >>> 0; d=c; c=b; b=a; a=(t1 + t2) >>> 0;
      }
      H[0]=(H[0]+a)>>>0; H[1]=(H[1]+b)>>>0; H[2]=(H[2]+c)>>>0; H[3]=(H[3]+d)>>>0;
      H[4]=(H[4]+e)>>>0; H[5]=(H[5]+f)>>>0; H[6]=(H[6]+g)>>>0; H[7]=(H[7]+h)>>>0;
    }
    var out = new Uint8Array(32);
    for (var i = 0; i < 8; i++) {
      out[i*4] = H[i] >>> 24; out[i*4+1] = (H[i] >>> 16) & 0xFF;
      out[i*4+2] = (H[i] >>> 8) & 0xFF; out[i*4+3] = H[i] & 0xFF;
    }
    return out;
  }
  function deriveSeed(hex, domain) {
    var sessionBytes = hexToBytes(hex), domainBytes = new TextEncoder().encode(domain),
        sepBytes = new TextEncoder().encode('aegis:per-site-seed:v2:');
    var msg = new Uint8Array(sessionBytes.length + sepBytes.length + domainBytes.length);
    msg.set(sessionBytes, 0); msg.set(sepBytes, sessionBytes.length);
    msg.set(domainBytes, sessionBytes.length + sepBytes.length);
    var digest = sha256Raw(msg), r = '';
    for (var i = 0; i < 16; i++) r += ('0' + digest[i].toString(16)).slice(-2);
    return r;
  }
  // 审计第六轮（2026-10-03）：站点种子不再经 defineProperty 导出为 window
  // 全局（P1）——applyNoise 是「种子 + 像素索引」的纯函数，页面按名读走
  // 种子、复刻 aegisNudge 与三枚 Math.imul 常数即可确定性去噪还原真画布；
  // 具名 __AEGIS_* 全局本身还是防护存在性的现成探针。对齐参照实现
  // core/rust-policy-core/src/per_site_seed.rs:24-28（「站点种子按域派生
  // 后仅存在于闭包内」）：种子改闭包局部 const，Stage 3/3c 两处消费点
  // 下移进本闭包（嵌套块整体缩进两级以示作用域边界——边界见本闭包尾注）。
  // 顶层站点框定（审计第六轮延续 2026-10-04）：参照实现
  // core/rust-policy-core/src/per_site_seed.rs:15-21（引 Brave）明确要求
  // "第三方帧与脚本共享顶层 eTLD+1 的种子"。本帧自身 hostname 派生会让
  // 同一第三方跟踪帧在所有站点产出**同一个**种子——画布哈希即成全平台
  // 持久标识符，恰好绕过本防护。Chromium/WebView 提供
  // location.ancestorOrigins（祖先 origin 链，跨源亦可见，[0] 为最顶层祖先），
  // 即所需通道，无需宿主下发（此前台账记为"无顶层源可达通道"，不准确）。
  // 不可用/为空（非 Chromium 内核、顶层文档）时保守退回本帧 hostname。
  function aegisHostFromOrigin(o) {
    var s = String(o || '');
    var i = s.indexOf('://');
    if (i >= 0) s = s.slice(i + 3);
    s = s.split('/')[0].split('?')[0];
    if (s.charAt(0) === '[') {           // IPv6 字面量：端口在 ] 之后
      var j = s.indexOf(']');
      return j >= 0 ? s.slice(0, j + 1) : s;
    }
    var k = s.lastIndexOf(':');
    return k >= 0 ? s.slice(0, k) : s;
  }
  function aegisTopLevelHostname() {
    try {
      var anc = location.ancestorOrigins;
      if (anc && anc.length > 0) {
        var h = aegisHostFromOrigin(anc[0]).toLowerCase();
        if (h) return h;
      }
    } catch (e) { /* 取不到即退回本帧口径——不得因顶层链失败而放弃噪声 */ }
    return location.hostname;
  }
  const __AEGIS_SITE_SEED = deriveSeed('$sessionSeed', getETLD1(aegisTopLevelHostname()));

  // === Stage 3: Canvas 噪声 ===
  // AD-212（2026-09-26 审计）：噪声施加在**离屏副本**上（参照 Rust 侧 RS-025
  // 修复模式）——原实现 getImageData/putImageData 破坏性写回活画布：①二次读
  // 同一画布结果不同（噪声注入自身可检测）；②页面后续渲染被永久污染。副本
  // 仅用于返回值，原 ctx 不动；且不调用源画布 getContext（drawImage 对任意
  // 上下文类型的源画布均可用，也避免把尚无上下文的画布永久锁定为 2d）。
${WebViewHardeningCanvas.js}
  // AD-258（2026-10-01 审计）：Stage 3 原有一个 WebGL getParameter 伪装包装，
  // 被 Stage 7 对同一常量（0x9245/0x9246）的先行返回遮蔽（永不可达死代码），
  // 且其返回值含品牌字符串（现成指纹标记）——已删除，伪装单源收敛 Stage 7。
  (function() {
    // 审计第六轮（2026-10-03）：种子消费点 2/2——同取外层 Stage 2 闭包常量
    //（种子全局导出已撤销，切片偏移 8..16 口径不变）。
    const seed = parseInt(__AEGIS_SITE_SEED.slice(8, 16), 16);
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 + (seed % 7) });
  })();
// 审计第六轮（2026-10-03）：Stage 2 闭包边界收口——站点种子自派生到两处
// 消费（canvas 噪声 / hardwareConcurrency）全程不出闭包，页面无可读句柄。
})();

        """.trimIndent()
}

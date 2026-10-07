//! FingerprintShield（照搬 voidbrowser privacy/fingerprint.rs 本地化适配）。
//!
//! 每会话生成加密随机种子，用于确定性地注入 JS 指纹噪声。
//! 所有 WebView 共享同一个会话种子，每次启动刷新。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：WebView 创建时调用 `inject_script()` 注入 JS。

use std::fmt;

mod canvas;

/// 指纹防护种子（32 字节加密随机）。
#[derive(Clone)]
pub struct FingerprintShield {
    seed: [u8; 32],
}

/// 公共后缀清单**单源**（R7-CS2-10·第七轮）：`include_str!` 是编译期读取，
/// 「核心无运行期 I/O」的约束不破。三端表体另有对账门禁
/// `contracts/codegen/verify_seed_framing_parity.py` 钉成同一集合——第七轮前 C#/Kotlin/Rust
/// 各持 54/51/31 条手抄表，同一用户在不同端拿到不同 eTLD+1。
const PUBLIC_SUFFIX_SOURCE: &str = include_str!("../../../contracts/policy/public-suffix-list.txt");

/// 渲染为 JS 对象字面量（`{ 'co.uk': 1, … }`——含外层花括号：模板里写
/// `{psl}` 时花括号由本函数提供，`format!` 只填值）。读空即 panic——清单
/// 路径被改/被清空时绝不静默退化成"没有公共后缀表"（那正是跨站关联面回归）。
fn public_suffix_table_js() -> String {
    let entries: Vec<String> = PUBLIC_SUFFIX_SOURCE
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(|entry| format!("'{entry}': 1"))
        .collect();
    assert!(
        !entries.is_empty(),
        "公共后缀清单为空——站点框定将退化，拒绝产出注入脚本"
    );
    format!("{{ {} }}", entries.join(", "))
}

impl fmt::Debug for FingerprintShield {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "FingerprintShield(seed=***hidden***)")
    }
}

impl FingerprintShield {
    /// 用系统加密随机源创建新会话种子。
    /// 此前用 SystemTime 纳秒 × PID 推导——完全可预测且 (i%16)*8 移位使
    /// 字节 0-15 与 16-31 相同（有效熵 ≤128bit 且结构相关），指纹噪声
    /// 可被外部推算复现。现在直接取 OS CSPRNG。
    pub fn new() -> Self {
        let mut seed = [0u8; 32];
        // RS-153：getrandom 0.3 API——getrandom() 更名 fill()
        if getrandom::fill(&mut seed).is_err() {
            // OS 随机源不可用（极端环境）——退化为时间+PID 混合（仍填充全部
            // 32 字节，高低半区经旋转与异或折叠去相关）
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            let pid = std::process::id() as u128;
            for (i, byte) in seed.iter_mut().enumerate() {
                let mut val = nanos ^ (pid << 32) ^ ((i as u128) << 24);
                val = val
                    .wrapping_mul(0x9E37_79B9_7F4A_7C15)
                    .rotate_right(((i * 7) % 128) as u32);
                *byte = (val as u8) ^ ((val >> 64) as u8) ^ (i as u8);
            }
        }
        Self { seed }
    }

    /// 从已有种子恢复（用于持久化/测试）。
    pub fn from_seed(seed: [u8; 32]) -> Self {
        Self { seed }
    }

    /// 种子的十六进制表示（注入 JS 时用）。
    ///
    /// RS-262（2026-10-01 审计）：收敛到 util::hex_encode 单源——此处逐字节
    /// format! 是 crate 内第三份 hex 实现（util::hex_encode / ffi/broker 查表
    /// 特化之外又一份），口径漂移面。
    pub fn seed_hex(&self) -> String {
        crate::util::hex_encode(&self.seed)
    }

    /// 种子的原始字节（供 PerSiteSeed 等管道阶段使用）。
    pub fn seed_bytes(&self) -> [u8; 32] {
        self.seed
    }

    /// 生成 JS 注入脚本（注入 WebView——canvas/Audio 噪声）。
    ///
    /// 种子以闭包内局部常量注入——**不再置于顶层全局词法环境**（此前顶层
    /// `const __AEGIS_SESSION_SEED` 任意页面可按名读取，全会话跨站唯一
    /// 标识符等于主动发放的超级 Cookie）。
    ///
    /// RS-026（审计 2026-09-24）：WebGL vendor/renderer 伪装已移出本模块——
    /// webgl_spoof 是该能力的单一负责方（此前两处覆盖同两个常量但取值
    /// 口径矛盾，后者静默遮蔽前者）。Canvas 噪声为本模块职责保留。
    ///
    /// RS-207（2026-09-26 审计）：canvas 噪声种子**按站点派生**——此前直接
    /// 取会话级常量 `__AEGIS_SESSION_SEED.slice(0,8)`，同一用户同会话访问
    /// A/B 两站噪声图案完全相同，站点比对 canvas 哈希即可跨站关联。
    /// R7-CS1-05≡R7-CS2-01（第七轮）：站点键取**顶层 eTLD+1**
    ///（`location.ancestorOrigins[0]` → eTLD+1，取不到才退回本帧 hostname）。
    /// 本帧口径下同一第三方跟踪帧在该用户的所有宿主站点上产出同一种子，
    /// 加噪画布哈希本身即成跨站持久标识符；参照实现 per_site_seed.rs:17-19
    /// 引 Brave 原文正是 "share the seed value of the top level eTLD+1 domain"。
    /// AudioBuffer 通道的 per-site 隔离由 PerSiteSeed 阶段（Rust 侧 SHA-256
    /// 派生）负责。
    pub fn inject_script(&self) -> String {
        let hex = self.seed_hex();
        // R7-CS2-10：公共后缀表单源——本模块不再手抄第二份表体
        let psl = public_suffix_table_js();
        // RS-218（2026-09-26 审计）：代理注册接口 Symbol 键单源引用
        //（描述串去品牌化——详见 ToStringGuard::REGISTER_SYMBOL）
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
        // ⑦：canvas 段外迁 shield/canvas.rs（本文件在零余量基线上），按原位置插回
        let canvas = canvas::canvas_js(reg_sym);
        format!(
            r#"
// Aegis FingerprintShield — 每会话确定性噪声种子（闭包封装——不进全局作用域）
(function() {{
  const __AEGIS_SESSION_SEED = '{hex}';

  // RS-207（2026-09-26 审计）：canvas 噪声站点键——FNV-1a 域混合 + 两轮
  // xorshift 雪崩；同站同会话确定（噪声稳定），跨站/跨会话去相关
  // RS-257（2026-10-01 审计）：eTLD+1 提取带公共后缀表——此前固定取
  // 最后两标签，a.co.uk 与 b.co.uk 共享种子（跨站关联面）。末两标签命中
  // 公共后缀表时升到三标签（公共后缀本身不构成站点边界）
  // R7-CS2-10：表体由 Rust 侧从 contracts/policy/public-suffix-list.txt 生成
  //（本模块不再手抄——第七轮实测三端手抄表 54/51/31 条，同一用户在不同端
  // 拿到不同 eTLD+1，user.github.io 一侧为 user.github.io、另一侧为 github.io，
  // 跨站关联面从侧门回来）
  var AEGIS_PUBLIC_SUFFIXES = {psl};
  function aegisEtldPlus1(host) {{
    var parts = host.split('.');
    if (parts.length <= 2) return host;
    var last2 = parts.slice(-2).join('.');
    if (AEGIS_PUBLIC_SUFFIXES[last2] && parts.length >= 3) {{
      return parts.slice(-3).join('.');
    }}
    return last2;
  }}
  // R7-CS1-05≡R7-CS2-01：站点键取**顶层** eTLD+1（与 Android 孪生
  // WebViewHardening.aegisTopLevelHostname 逐字同口径）。Chromium/WebView 的
  // location.ancestorOrigins 给出祖先 origin 链（跨源亦可见，[0] 为最顶层祖先），
  // 无需宿主下发；取不到时保守退回本帧 hostname——绝不因顶层链失败而放弃噪声。
  function aegisHostFromOrigin(o) {{
    var s = String(o || '');
    var i = s.indexOf('://');
    if (i >= 0) s = s.slice(i + 3);
    s = s.split('/')[0].split('?')[0];
    if (s.charAt(0) === '[') {{            // IPv6 字面量：端口在 ] 之后
      var j = s.indexOf(']');
      return j >= 0 ? s.slice(0, j + 1) : s;
    }}
    var k = s.lastIndexOf(':');
    return k >= 0 ? s.slice(0, k) : s;
  }}
  function aegisTopLevelHostname() {{
    try {{
      var anc = location.ancestorOrigins;
      if (anc && anc.length > 0) {{
        var h = aegisHostFromOrigin(anc[0]).toLowerCase();
        if (h) return h;
      }}
    }} catch (e) {{ /* 退回本帧口径 */ }}
    return location.hostname;
  }}
  function aegisCanvasSeed() {{
    var etld1 = aegisEtldPlus1(aegisTopLevelHostname() || '');
    var h = 2166136261 >>> 0;
    for (var i = 0; i < etld1.length; i++) {{
      h = Math.imul(h ^ etld1.charCodeAt(i), 16777619) >>> 0;
      h = (h ^ __AEGIS_SESSION_SEED.charCodeAt(i % 64)) >>> 0;
    }}
    // R8-RS-02（第八轮审计 2026-10-04）：会话种子必须无条件混入。上面那条
    // 循环以 etld1.length 为界——hostname 取不到（about:srcdoc 派生 worker、
    // opaque origin、location.hostname 为空）时循环零次执行，种子退化为与会话
    // 无关的常量：所有用户所有站点拿到同一噪声，既等于没有噪声，又反过来成为
    // 「Aegis 用户」的跨站共享标识符。补一轮全 64 字符混入后，空站点键亦有
    // 2^256 量级的输入。worker 出口仍只能拿到本帧 host（WorkerLocation 无
    // ancestorOrigins）——那部分是宿主下发顶层域的接口缺口，记 R8-RS-15。
    for (var s = 0; s < 64; s++) {{
      h = Math.imul(h ^ __AEGIS_SESSION_SEED.charCodeAt(s), 16777619) >>> 0;
    }}
    h ^= h >>> 15; h = Math.imul(h, 2246822519) >>> 0;
    h ^= h >>> 13; h = Math.imul(h, 3266489917) >>> 0;
    h ^= h >>> 16;
    return h >>> 0;
  }}

{canvas}

// 音频指纹噪声由 PerSiteSeed（RS-028）负责——按站点隔离，不在此模块重复

// hardwareConcurrency 随机化（2-8 核）
// RS-250（2026-10-01 审计）：原型级 getter 替换——此前实例遮蔽
// （defineProperty(navigator, ...)）可经
// Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency')
// .get.call(navigator) 直取原值（与 letterbox/font_norm 口径统一为原型级）。
// 保留原 descriptor 的 enumerable/configurable（属性形态对齐原生）
(function() {{
  // RS-292（2026-10-02 审计）：worker 作用域守卫——Navigator 在 worker
  // 未定义，裸引用即抛未捕获 ReferenceError（脚本整体中断）
  if (typeof Navigator === 'undefined') return;
  const seed = parseInt(__AEGIS_SESSION_SEED.slice(8, 16), 16);
  var oHC = Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency');
  if (oHC && oHC.get) {{
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
      get: function() {{ return 2 + (seed % 7); }},
      enumerable: oHC.enumerable,
      configurable: oHC.configurable
    }});
  }}
}})();
}})();
"#
        )
    }
}

impl Default for FingerprintShield {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod noise_tests;
#[cfg(test)]
mod tests;

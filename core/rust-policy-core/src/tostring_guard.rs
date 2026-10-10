// 由账号2生成
//! ToStringGuard（参照 playwright-afp Function.prototype.toString 欺骗）。
//!
//! 覆盖 Function.prototype.toString()，使被代理的函数返回原始函数的
//! 源代码表示，防止指纹检测脚本发现注入的代理。
//!
//! 原始版权声明：
//!   playwright-afp by pavlealeksic (MIT License)
//!   https://github.com/pavlealeksic/playwright-afp
//!
//! 原理：指纹检测脚本会调用 `HTMLCanvasElement.prototype.toDataURL.toString()`
//! 来检查函数是否被修改。如果返回包含 "proxy" 或非原始源码，检测脚本会标记
//! 该浏览器为"被篡改"。ToStringGuard 使所有被代理的函数返回原始 toString。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 FingerprintShield 管线中作为独立阶段调用。

use std::fmt;

/// ToStringGuard — Function.prototype.toString 欺骗。
///
/// 使所有被代理的函数返回原始 toString 值，
/// 防止指纹检测脚本发现注入的代理。
pub struct ToStringGuard;

impl fmt::Debug for ToStringGuard {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "ToStringGuard")
    }
}

impl ToStringGuard {
    /// 创建 ToStringGuard 实例。
    pub fn new() -> Self {
        Self
    }

    /// 代理注册接口的 Symbol 键（RS-027 单源——模块注入方共用同一常量）。
    ///
    /// RS-027（审计 2026-09-24）：注册接口从具名全局常量
    /// `window.__AEGIS_REGISTER_PROXY` 收敛到 Symbol 键——
    /// `Object.keys`/`for-in`/`getOwnPropertyNames` 均不可见，通用指纹
    /// 脚本按名探测落空。
    ///
    /// RS-218（2026-09-26 审计）：口径修正 + 去品牌化——Symbol 键**并非
    /// 不可枚举**：`Object.getOwnPropertySymbols(window)` 无需猜测描述串
    /// 即可列出全部 Symbol 属性，再按 `Symbol.for(desc)` 取用注册接口。
    /// Symbol 收敛的真实收益是「按**具名字符串**探测落空 + 不出现在
    /// 字符串枚举通道」，而非不可发现。描述串去品牌化（移除 "aegis."
    /// 前缀）——Symbol 描述本身即探测信号，品牌名直指防护存在。
    pub const REGISTER_SYMBOL: &'static str = "proxy.register.v1";

    /// R8-RS-09：注册窗口关闭入口的 Symbol 键。与 `REGISTER_SYMBOL` 互不为
    /// 子串——既有计数类用例按 `Symbol.for('proxy.register.v1')` 统计，不能被本键误命中。
    pub const CLOSE_SYMBOL: &'static str = "proxy.register.close.v1";

    /// 生成 toString 欺骗 JS 注入脚本。
    ///
    /// 覆盖 Function.prototype.toString 和 Function.prototype.toLocaleString，
    /// 使被代理的函数返回原始函数的 toString 值。
    ///
    /// 使用 WeakMap 存储代理→原始函数映射，
    /// 当代理函数调用 toString() 时返回原始函数的 toString。
    pub fn inject_script(&self) -> String {
        format!(
            r#"
// Aegis ToStringGuard — Function.prototype.toString 欺骗（参照 playwright-afp）
// 原始设计：pavlealeksic/playwright-afp (MIT License)
// 使被代理的函数返回原始 toString，防止检测脚本发现注入的代理
(function() {{
  // 存储代理函数→原始函数映射
  var proxyMap = new WeakMap();

  // 覆盖 toString
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {{
    // 如果是代理函数，返回原始函数的 toString
    if (proxyMap.has(this)) {{
      return origToString.call(proxyMap.get(this));
    }}
    return origToString.call(this);
  }};

  // 覆盖 toLocaleString
  var origToLocale = Function.prototype.toLocaleString;
  Function.prototype.toLocaleString = function() {{
    if (proxyMap.has(this)) {{
      return origToLocale.call(proxyMap.get(this));
    }}
    return origToLocale.call(this);
  }};

  // 自注册本模块覆盖的函数——toString 自身的 toString 亦返回原始实现，
  // 否则"检测 toString 是否被覆盖"本身即可识破防护（此前 proxyMap 恒空，
  // 注册接口无任何调用者，欺骗防护实际为零）
  proxyMap.set(Function.prototype.toString, origToString);
  proxyMap.set(Function.prototype.toLocaleString, origToLocale);

  // RS-027：注册接口收敛到 Symbol 键——不出现在字符串枚举通道
  //（Object.keys / for-in / getOwnPropertyNames / JSON.stringify）。
  // RS-218（2026-09-26 审计）：Symbol 键仍可被 getOwnPropertySymbols 列出
  //（非不可发现）——收益是具名字符串探测落空；描述串已去品牌化
  var KEY = Symbol.for('{sym}');
  var CLOSE_KEY = Symbol.for('{close_sym}');
  // R8-RS-09（第八轮 2026-10-06）：注册资格改由**闭包内的 open 标志**决定。
  // RS-252 原设计是「窗口期结束后把 window 上的属性替换成惰性函数」——那挡不住
  // 替换之前已拿到引用的调用方，且撤销排在注入脚本之后的宏任务里，而
  // document-start 注入与后续 HTML 解析在**同一个任务**内完成 ⇒ 头部内联脚本
  // 在撤销之前就能注册。现由管线末尾同步关掉标志（`close_script()`），页面脚本
  // 在此之后才有执行机会 ⇒ 窗口为零；引用被捕获也无用（函数体自己失效）。
  var open = true;
  Object.defineProperty(window, KEY, {{
    value: function(proxy, original) {{
      if (!open) return;
      // RS-252（2026-10-01 审计）：注册接口参数防御——页面拿到注册函数后
      // 可注入伪造映射（自身钩子伪装成原生实现）。双函数校验 + original
      // 不得是已注册代理（链式注册 proxy→proxy 会让包装源码经 toString
      // 泄漏给任意后续注册者）
      if (typeof proxy !== 'function' || typeof original !== 'function') return;
      // R8-RS-09：proxy 侧同样要断。此前只查 original，于是可以把**我方包装函数**
      // 重新登记到另一个原生上——同一函数在不同读取通道给出不同 toString，
      // 不一致本身就是检测信号，且把我方防护变成攻击者的伪装件。
      if (proxyMap.has(proxy)) return;
      // R9-AD-1（第九轮 2026-10-10）：链式包装必须**传递解析**到最底层原生。
      // RS-252 原写法是「original 已在表里就拒绝登记」——拒绝的动机对（登记
      // proxy→proxy 会让 origToString.call(内层包装) 把包装源码吐出去），但结论错：
      // 被拒的是**最外层**，它永不在表里 ⇒ outer.toString() 直接返回我方包装源码，
      // 比登记更糟。解析后 outer→native，toString 得 `function {{}} [native code]` 形态。
      // hops 上限防环（登记只发生在闭包窗口内、由我方代码执行，但成环代价是死循环）。
      var target = original;
      var hops = 0;
      while (proxyMap.has(target) && hops < 8) {{
        target = proxyMap.get(target);
        hops = hops + 1;
      }}
      proxyMap.set(proxy, target);
    }},
    // 不可替换：撤销只靠标志，不留「把属性换成别的函数」这条路
    writable: false,
    configurable: false
  }});
  // 关闭入口：幂等、不可替换。页面唯一能用它做的事是**提前**关窗，
  // 那只缩小攻击面（fail-closed 方向），所以不必hid 它。
  Object.defineProperty(window, CLOSE_KEY, {{
    value: function() {{
      open = false;
    }},
    writable: false,
    configurable: false
  }});
}})();
"#,
            sym = Self::REGISTER_SYMBOL,
            close_sym = Self::CLOSE_SYMBOL
        )
    }
}

impl ToStringGuard {
    /// 管线**末尾**追加的一行：关掉本 blob 的注册窗口（R8-RS-09）。
    ///
    /// 由 `protection_mode::fingerprint_pipeline_with_mode` 在所有阶段之后发射：
    /// document-start 注入先于页面脚本执行，各阶段登记完成后窗口即闭合，页面从未
    /// 获得过一次注册机会。RS-252 的 `setTimeout(0)` 撤销做不到——宏任务排在解析
    /// 任务之后，头部内联脚本在那之前仍可注册伪造映射。
    #[must_use]
    pub fn close_script() -> String {
        let mut s = String::from("(function() { var c = window[Symbol.for('");
        s.push_str(Self::CLOSE_SYMBOL);
        s.push_str("'); if (c) c(); })();");
        s
    }
}

impl Default for ToStringGuard {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests;

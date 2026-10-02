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
  Object.defineProperty(window, KEY, {{
    value: function(proxy, original) {{
      // RS-252（2026-10-01 审计）：注册接口参数防御——页面拿到注册函数后
      // 可注入伪造映射（自身钩子伪装成原生实现）。双函数校验 + original
      // 不得是已注册代理（链式注册 proxy→proxy 会让包装源码经 toString
      // 泄漏给任意后续注册者）
      if (typeof proxy !== 'function' || typeof original !== 'function') return;
      if (proxyMap.has(original)) return;
      proxyMap.set(proxy, original);
    }},
    // RS-252：configurable: true 仅限注入窗口期（撤销通道）——注入窗口后
    // 统一替换为惰性函数并锁死 configurable: false（见下方 setTimeout）
    writable: false,
    configurable: true
  }});

  // RS-252：注入窗口后撤销——各防护阶段脚本经 document-start 同步注入完毕
  // 后（setTimeout(0) 宏任务），注册接口替换为惰性函数并锁死。页面脚本
  // 无法在本任务内先行执行（document-start 先于页面脚本），窗口闭合后
  // 伪造映射不再可注入；窗口期内页面仍可调用是残余面（original 未注册
  // 校验限制其只能注册真原生函数对）。
  setTimeout(function() {{
    try {{
      Object.defineProperty(window, KEY, {{
        value: function() {{}},
        writable: false,
        configurable: false
      }});
    }} catch (e) {{}}
  }}, 0);
}})();
"#,
            sym = Self::REGISTER_SYMBOL
        )
    }
}

impl Default for ToStringGuard {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn script_contains_proxy_map() {
        let guard = ToStringGuard::new();
        let script = guard.inject_script();
        assert!(script.contains("WeakMap"));
        assert!(script.contains("Symbol.for"));
        assert!(script.contains("Function.prototype.toString"));
    }

    #[test]
    fn script_exposes_register_interface() {
        let guard = ToStringGuard::new();
        let script = guard.inject_script();
        assert!(script.contains("proxyMap.set(proxy, original)"));
    }

    #[test]
    fn script_self_registers_own_overrides() {
        // RS-007 回归：guard 覆盖的 toString/toLocaleString 必须自注册进
        // proxyMap——否则映射恒空、欺骗防护为零
        let script = guard_script();
        assert!(script.contains("proxyMap.set(Function.prototype.toString, origToString)"));
        assert!(script.contains("proxyMap.set(Function.prototype.toLocaleString, origToLocale)"));
    }

    #[test]
    fn register_interface_symbol_keyed_not_named_global() {
        // RS-027 回归：注册接口收敛到 Symbol 键——不再有具名全局常量
        let script = guard_script();
        assert!(script.contains(&format!("Symbol.for('{}')", ToStringGuard::REGISTER_SYMBOL)));
        assert!(
            !script.contains("__AEGIS_REGISTER_PROXY"),
            "具名全局注册接口必须移除"
        );
    }

    fn guard_script() -> String {
        ToStringGuard::new().inject_script()
    }

    // —— RS-080 回归（审计 2026-09-25） ——

    #[test]
    fn to_locale_string_coverage_independent() {
        // RS-080：toLocaleString 与 toString 是两条独立欺骗通道——检测
        // 方可走任一路径，二者必须都进 proxyMap
        let script = guard_script();
        assert!(
            script.contains("Function.prototype.toLocaleString = function()"),
            "toLocaleString 独立覆盖"
        );
        assert!(
            script.contains("origToLocale.call(proxyMap.get(this))"),
            "toLocaleString 代理欺骗路径"
        );
        assert!(script.contains("proxyMap.set(Function.prototype.toLocaleString, origToLocale)"));
    }

    #[test]
    fn register_interface_tamper_proofed() {
        // RS-080/RS-252：注册接口防篡改——writable: false（页面不可偷换注册
        // 函数为收集代理的陷阱）；configurable 在注入窗口期为 true（撤销
        // 通道），窗口期后经 setTimeout 锁死为 false（见下方专项测试）
        let script = guard_script();
        assert!(
            script.contains("writable: false,\n    configurable: true"),
            "注入窗口期：只读但可撤销（RS-252 撤销通道）"
        );
        assert!(
            script.contains("writable: false,\n        configurable: false"),
            "窗口期后：惰性函数 + 双 false 锁死"
        );
        assert!(
            !script.contains("enumerable: true"),
            "注册接口不得可枚举（泄漏进 Object.keys）"
        );
    }

    // —— RS-252 回归（审计 2026-10-01）：注册接口参数防御 + 注入窗口撤销 ——

    #[test]
    fn register_interface_validates_arguments() {
        // RS-252：注册函数必须校验双函数入参 + original 未注册——页面拿到
        // 注册接口后不得注入伪造映射（非函数对/链式 proxy→proxy 注册）
        let script = guard_script();
        assert!(
            script.contains("typeof proxy !== 'function' || typeof original !== 'function'"),
            "双函数类型校验"
        );
        assert!(
            script.contains("if (proxyMap.has(original)) return;"),
            "original 不得是已注册代理（链式注册泄漏包装源码）"
        );
        // 校验先于登记
        let check = script
            .find("if (proxyMap.has(original)) return;")
            .expect("校验存在");
        let set = script
            .find("proxyMap.set(proxy, original);")
            .expect("登记存在");
        assert!(check < set, "校验必须先于登记");
    }

    #[test]
    fn register_interface_revoked_after_injection_window() {
        // RS-252：注入窗口后撤销——setTimeout(0) 宏任务把注册接口替换为
        // 惰性函数并锁死（document-start 阶段脚本全部同步完成后窗口闭合）
        let script = guard_script();
        assert!(
            script.contains("setTimeout(function() {"),
            "撤销必须经宏任务延迟（等 document-start 注入完成）"
        );
        assert!(
            script.contains("value: function() {},"),
            "撤销后替换为惰性函数（不再接受注册）"
        );
    }
}

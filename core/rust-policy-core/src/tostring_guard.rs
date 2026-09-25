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
    /// 脚本按名探测落空（须先猜测 Symbol 描述串才可能触达）。
    pub const REGISTER_SYMBOL: &'static str = "aegis.proxy.register.v1";

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

  // RS-027：注册接口收敛到 Symbol 键——Symbol 属性不出现在任何
  // 枚举通道（Object.keys / for-in / getOwnPropertyNames / JSON.stringify），
  // 通用指纹脚本按名探测落空
  var KEY = Symbol.for('{sym}');
  Object.defineProperty(window, KEY, {{
    value: function(proxy, original) {{
      proxyMap.set(proxy, original);
    }},
    writable: false,
    configurable: false
  }});
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
}

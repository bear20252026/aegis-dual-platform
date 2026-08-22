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

    /// 生成 toString 欺骗 JS 注入脚本。
    ///
    /// 覆盖 Function.prototype.toString 和 Function.prototype.toLocaleString，
    /// 使被代理的函数返回原始函数的 toString 值。
    ///
    /// 使用 WeakMap 存储代理→原始函数映射，
    /// 当代理函数调用 toString() 时返回原始函数的 toString。
    pub fn inject_script(&self) -> String {
        r#"
// Aegis ToStringGuard — Function.prototype.toString 欺骗（参照 playwright-afp）
// 原始设计：pavlealeksic/playwright-afp (MIT License)
// 使被代理的函数返回原始 toString，防止检测脚本发现注入的代理
(function() {
  // 存储代理函数→原始函数映射
  var proxyMap = new WeakMap();

  // 覆盖 toString
  var origToString = Function.prototype.toString;
  Function.prototype.toString = function() {
    // 如果是代理函数，返回原始函数的 toString
    if (proxyMap.has(this)) {
      return origToString.call(proxyMap.get(this));
    }
    return origToString.call(this);
  };

  // 覆盖 toLocaleString
  var origToLocale = Function.prototype.toLocaleString;
  Function.prototype.toLocaleString = function() {
    if (proxyMap.has(this)) {
      return origToLocale.call(proxyMap.get(this));
    }
    return origToLocale.call(this);
  };

  // 暴露注册接口——其他模块注入代理时调用
  Object.defineProperty(window, '__AEGIS_REGISTER_PROXY', {
    value: function(proxy, original) {
      proxyMap.set(proxy, original);
    },
    writable: false,
    configurable: false
  });
})();
"#
        .to_string()
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
        assert!(script.contains("__AEGIS_REGISTER_PROXY"));
        assert!(script.contains("Function.prototype.toString"));
    }

    #[test]
    fn script_exposes_register_interface() {
        let guard = ToStringGuard::new();
        let script = guard.inject_script();
        assert!(script.contains("proxyMap.set(proxy, original)"));
    }
}

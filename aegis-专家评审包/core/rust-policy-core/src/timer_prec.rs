// 由账号2生成
//! TimerPrecision（参照 Mullvad Browser 定时器精度降低策略）。
//!
//! 降低 JavaScript 定时器 API 的精度，防止基于高精度计时的指纹识别。
//! 默认精度 1000μs（1ms）+ 随机 jitter，与 Mullvad Browser 一致。
//!
//! 原始版权声明：
//!   Mullvad Browser timer precision reduction by Mullvad VPN / Tor Project
//!   Licensed under MPL-2.0
//!   https://mullvad.net/en/browser/hard-facts
//!
//! 原始配置（Mullvad about:config）：
//!   privacy.resistFingerprinting.reduceTimerPrecision.microseconds = 1000
//!   privacy.resistFingerprinting.reduceTimerPrecision.jitter = true
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：在 FingerprintShield 管线中作为独立阶段调用。

use std::fmt;

/// 定时器精度降低配置。
#[derive(Debug, Clone)]
pub struct TimerPrecisionConfig {
    /// 精度（微秒）——默认 1000μs = 1ms。
    pub microseconds: u32,
    /// 是否添加随机 jitter（防统计检测）。
    pub jitter: bool,
}

impl Default for TimerPrecisionConfig {
    fn default() -> Self {
        Self {
            microseconds: 1000,
            jitter: true,
        }
    }
}

/// TimerPrecision — 定时器精度降低防护。
///
/// 覆盖 `performance.now()`、`Date.now()`、`new Date()` 等
/// 高精度计时 API，使返回值圆整到配置的精度。
pub struct TimerPrecision {
    config: TimerPrecisionConfig,
}

impl fmt::Debug for TimerPrecision {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "TimerPrecision({}μs, jitter={})",
            self.config.microseconds, self.config.jitter
        )
    }
}

impl TimerPrecision {
    /// 用默认配置创建（1000μs + jitter）。
    pub fn new() -> Self {
        Self {
            config: TimerPrecisionConfig::default(),
        }
    }

    /// 用自定义配置创建。
    pub fn with_config(config: TimerPrecisionConfig) -> Self {
        Self { config }
    }

    /// 生成定时器精度降低 JS 注入脚本。
    ///
    /// 覆盖：
    /// - `performance.now()` — 圆整到 microseconds
    /// - `performance.now()` 的 jitter（如果启用）
    /// - `Date.now()` — 圆整到 microseconds
    ///
    /// 不覆盖 `new Date()`（构造函数无法安全覆盖），
    /// 但 `Date.now()` 是主要的高精度计时来源。
    pub fn inject_script(&self) -> String {
        let us = self.config.microseconds;
        let jitter = self.config.jitter;
        format!(
            r#"
// Aegis TimerPrecision — 定时器精度降低（参照 Mullvad Browser）
// 原始策略：Mullvad VPN / Tor Project (MPL-2.0)
// 精度：{us}μs，jitter：{jitter}
(function() {{
  var PRECISION_US = {us};
  var PRECISION_MS = PRECISION_US / 1000;
  var JITTER_ENABLED = {jitter};

  function reducePrecision(value) {{
    // 圆整到精度边界
    var rounded = Math.round(value / PRECISION_MS) * PRECISION_MS;
    // 添加 jitter（±50% 精度范围内的随机偏移）
    if (JITTER_ENABLED) {{
      var jitterRange = PRECISION_MS / 2;
      rounded += (Math.random() - 0.5) * jitterRange;
    }}
    return rounded;
  }}

  // 覆盖 performance.now()
  try {{
    var origPerfNow = performance.now.bind(performance);
    Object.defineProperty(performance, 'now', {{
      value: function() {{ return reducePrecision(origPerfNow()); }},
      writable: false,
      configurable: false
    }});
  }} catch(e) {{}}

  // 覆盖 Date.now()
  try {{
    var origDateNow = Date.now;
    Date.now = function() {{ return reducePrecision(origDateNow()); }};
  }} catch(e) {{}}
}})();
"#
        )
    }
}

impl Default for TimerPrecision {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_is_1000us_with_jitter() {
        let config = TimerPrecisionConfig::default();
        assert_eq!(config.microseconds, 1000);
        assert!(config.jitter);
    }

    #[test]
    fn script_contains_precision_value() {
        let tp = TimerPrecision::new();
        let script = tp.inject_script();
        assert!(script.contains("1000"));
        assert!(script.contains("performance.now"));
        assert!(script.contains("Date.now"));
        assert!(script.contains("reducePrecision"));
    }

    #[test]
    fn custom_config_reflected() {
        let config = TimerPrecisionConfig {
            microseconds: 100,
            jitter: false,
        };
        let tp = TimerPrecision::with_config(config);
        let script = tp.inject_script();
        assert!(script.contains("100"));
        assert!(script.contains("false"));
    }

    #[test]
    fn debug_format_shows_config() {
        let tp = TimerPrecision::new();
        let debug = format!("{:?}", tp);
        assert!(debug.contains("1000"));
        assert!(debug.contains("jitter=true"));
    }
}

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
        // RS-020（审计 2026-09-24）：microseconds=0 饱和到 1——0 会让注入
        // JS 的 PRECISION_MS=0，`value / 0` 得 Infinity（精度降低完全失效）
        let us = self.config.microseconds.max(1);
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
    var wrappedPerfNow = function() {{ return reducePrecision(origPerfNow()); }};
    Object.defineProperty(performance, 'now', {{
      value: wrappedPerfNow,
      writable: false,
      configurable: false
    }});
    var reg1 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg1) reg1(wrappedPerfNow, origPerfNow);
  }} catch(e) {{}}

  // 覆盖 Date.now()
  try {{
    var origDateNow = Date.now;
    Date.now = function() {{ return reducePrecision(origDateNow()); }};
    var reg2 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg2) reg2(Date.now, origDateNow);
  }} catch(e) {{}}

  // RS-074（审计 2026-09-25）：mark/measure/timeStamp 的 startTime 与
  // duration 不经 JS 可见的 performance.now——宿主内部时钟直取，仅覆盖
  // now 属性拦不住这条路径，必须独立圆整
  try {{
    var origMark = performance.mark;
    performance.mark = function(name, options) {{
      if (options && typeof options.startTime === 'number') {{
        options = Object.assign({{}}, options, {{ startTime: reducePrecision(options.startTime) }});
      }}
      return origMark.call(this, name, options);
    }};
    var reg3 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg3) reg3(performance.mark, origMark);
  }} catch(e) {{}}

  try {{
    var origMeasure = performance.measure;
    performance.measure = function(name, start, end) {{
      var entry = origMeasure.call(this, name, start, end);
      try {{
        // entry 的 duration/timeStamp 是原型 getter——实例属性遮蔽圆整
        Object.defineProperty(entry, 'duration', {{ value: reducePrecision(entry.duration) }});
        Object.defineProperty(entry, 'startTime', {{ value: reducePrecision(entry.startTime) }});
      }} catch (e2) {{}}
      return entry;
    }};
    var reg4 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg4) reg4(performance.measure, origMeasure);
  }} catch(e) {{}}

  try {{
    var origRAF = window.requestAnimationFrame;
    window.requestAnimationFrame = function(cb) {{
      if (typeof cb !== 'function') return origRAF.call(window, cb);
      return origRAF.call(window, function(ts) {{ cb(reducePrecision(ts)); }});
    }};
    var reg5 = window[Symbol.for('aegis.proxy.register.v1')]; if (reg5) reg5(window.requestAnimationFrame, origRAF);
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

    // —— RS-073 回归（审计 2026-09-25） ——

    #[test]
    fn zero_microseconds_saturates_to_one() {
        // RS-073/RS-020：microseconds=0 饱和到 1——PRECISION_MS=0 会让
        // value/0 得 Infinity（精度降低完全失效）
        let tp = TimerPrecision::with_config(TimerPrecisionConfig {
            microseconds: 0,
            jitter: false,
        });
        let script = tp.inject_script();
        assert!(script.contains("PRECISION_US = 1;"), "0 必须饱和到 1");
        assert!(!script.contains("PRECISION_US = 0;"));
    }

    #[test]
    fn jitter_toggle_reflected() {
        // RS-073：jitter 开关透传进脚本（统计检测面语义）
        let on = TimerPrecision::new().inject_script();
        assert!(on.contains("JITTER_ENABLED = true"));
        let off = TimerPrecision::with_config(TimerPrecisionConfig {
            microseconds: 1000,
            jitter: false,
        })
        .inject_script();
        assert!(off.contains("JITTER_ENABLED = false"));
    }

    // —— RS-074 回归（审计 2026-09-25） ——

    #[test]
    fn high_resolution_channels_covered() {
        // RS-074：mark/measure/rAF 的计时面必须独立圆整——它们直取宿主
        // 内部时钟，不经 JS 可见的 performance.now
        let script = TimerPrecision::new().inject_script();
        assert!(script.contains("performance.mark"), "mark 覆盖");
        assert!(
            script.contains("startTime: reducePrecision(options.startTime)"),
            "mark 的显式 startTime 圆整"
        );
        assert!(script.contains("performance.measure"), "measure 覆盖");
        assert!(
            script.contains("'duration', { value: reducePrecision(entry.duration) }"),
            "measure 返回的 duration 圆整"
        );
        assert!(
            script.contains("requestAnimationFrame"),
            "rAF timestamp 圆整"
        );
        assert!(
            script.contains("cb(reducePrecision(ts))"),
            "rAF 回调时间戳经 reducePrecision"
        );
    }
}

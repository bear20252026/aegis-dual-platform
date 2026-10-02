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
    /// - `Date.now()` — 圆整到 microseconds（RS-208：恒取整——原生值无小数）
    /// - mark/measure/rAF/getEntries* 家族（RS-074/RS-217）
    /// - `Event.prototype.timeStamp` 与 `performance.timeOrigin`（RS-244）
    ///
    /// 不覆盖 `new Date()`（构造函数无法安全覆盖），
    /// 但 `Date.now()` 是主要的高精度计时来源。
    pub fn inject_script(&self) -> String {
        // RS-020（审计 2026-09-24）：microseconds=0 饱和到 1——0 会让注入
        // JS 的 PRECISION_MS=0，`value / 0` 得 Infinity（精度降低完全失效）
        let us = self.config.microseconds.max(1);
        let jitter = self.config.jitter;
        // RS-218（2026-09-26 审计）：代理注册接口 Symbol 键单源引用
        //（描述串去品牌化——详见 ToStringGuard::REGISTER_SYMBOL）
        let reg_sym = crate::tostring_guard::ToStringGuard::REGISTER_SYMBOL;
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
    // RS-216（2026-09-26 审计）：属性描述符对齐原生——双 false 形态可被
    // getOwnPropertyDescriptor 一查即破。
    // RS-250（2026-10-01 审计）：原型级替换（保留原 descriptor 属性）——
    // 此前实例 value 遮蔽可经 Performance.prototype.now.call(performance)
    // 直取原实现。原型 descriptor 优先，实例形态兜底（引擎定义位差异）
    var oPN = Object.getOwnPropertyDescriptor(Performance.prototype, 'now');
    var tgtPN = Performance.prototype;
    if (!oPN) {{
      oPN = Object.getOwnPropertyDescriptor(performance, 'now');
      tgtPN = performance;
    }}
    if (oPN) {{
      Object.defineProperty(tgtPN, 'now', {{
        value: wrappedPerfNow,
        writable: oPN.writable,
        enumerable: oPN.enumerable,
        configurable: oPN.configurable
      }});
    }}
    var reg1 = window[Symbol.for('{reg_sym}')]; if (reg1) reg1(wrappedPerfNow, origPerfNow);
  }} catch(e) {{}}

  // 覆盖 Date.now()
  // RS-208（2026-09-26 审计）：Math.round 取整——jitter 开启时
  // reducePrecision 返回带小数（±50% 精度随机偏移），原生 Date.now 恒为
  // 整数毫秒，Number.isInteger(Date.now()) 一行即识破防护。jitter 仅保留
  // 给 performance.now（Android 孪生 AD-108 同口径）
  try {{
    var origDateNow = Date.now;
    Date.now = function() {{ return Math.round(reducePrecision(origDateNow())); }};
    var reg2 = window[Symbol.for('{reg_sym}')]; if (reg2) reg2(Date.now, origDateNow);
  }} catch(e) {{}}

  // RS-074（审计 2026-09-25）：mark/measure/timeStamp 的 startTime 与
  // duration 不经 JS 可见的 performance.now——宿主内部时钟直取，仅覆盖
  // now 属性拦不住这条路径，必须独立圆整
  try {{
    var origMark = performance.mark;
    // RS-278（2026-10-02 审计）：mark 返回的 entry 此前原样透传——
    // startTime 经宿主内部时钟（绕过 JS 可见的 performance.now），
    // entry 的 startTime/duration 是高精度原值。返回前统一走
    // aegisRoundEntry 圆整（RS-296：WeakSet 保证双通道只圆整一次）
    var wrappedMark = function(name, options) {{
      if (options && typeof options.startTime === 'number') {{
        options = Object.assign({{}}, options, {{ startTime: reducePrecision(options.startTime) }});
      }}
      return aegisRoundEntry(origMark.call(this, name, options));
    }};
    // RS-279（2026-10-02 审计）：原型级 defineProperty（保留原 descriptor
    // 形态）——照 RS-250 now/timeOrigin 口径。此前实例 value 遮蔽可经
    // Performance.prototype.mark.call(performance, ...) 直取原实现
    var oPM = Object.getOwnPropertyDescriptor(Performance.prototype, 'mark');
    var tgtPM = Performance.prototype;
    if (!oPM) {{
      oPM = Object.getOwnPropertyDescriptor(performance, 'mark');
      tgtPM = performance;
    }}
    if (oPM) {{
      Object.defineProperty(tgtPM, 'mark', {{
        value: wrappedMark,
        writable: oPM.writable,
        enumerable: oPM.enumerable,
        configurable: oPM.configurable
      }});
    }}
    var reg3 = window[Symbol.for('{reg_sym}')]; if (reg3) reg3(wrappedMark, origMark);
  }} catch(e) {{}}

  try {{
    var origMeasure = performance.measure;
    // RS-296（2026-10-02 审计）：measure 直读与 getEntries* 缓冲区读取是
    // 同一 entry 对象的两条通道——统一走 aegisRoundEntry 单源圆整
    //（WeakSet 标记单次，独立圆整会叠加两份 jitter，双通道不一致可检测）
    var wrappedMeasure = function(name, start, end) {{
      return aegisRoundEntry(origMeasure.call(this, name, start, end));
    }};
    // RS-279：原型级 defineProperty（保留原 descriptor 形态，RS-250 口径）
    var oPMe = Object.getOwnPropertyDescriptor(Performance.prototype, 'measure');
    var tgtPMe = Performance.prototype;
    if (!oPMe) {{
      oPMe = Object.getOwnPropertyDescriptor(performance, 'measure');
      tgtPMe = performance;
    }}
    if (oPMe) {{
      Object.defineProperty(tgtPMe, 'measure', {{
        value: wrappedMeasure,
        writable: oPMe.writable,
        enumerable: oPMe.enumerable,
        configurable: oPMe.configurable
      }});
    }}
    var reg4 = window[Symbol.for('{reg_sym}')]; if (reg4) reg4(wrappedMeasure, origMeasure);
  }} catch(e) {{}}

  // RS-217（2026-09-26 审计）：getEntries* 家族——缓冲区读取通道直取宿主
  // 内部时钟，此前仅圆整 measure() 直接返回的 entry 与 mark 的显式
  // startTime，getEntries/getEntriesByName/getEntriesByType 返回的条目
  // 仍是原值。统一经实例属性遮蔽圆整 startTime/duration（与 measure 同型）
  //
  // RS-296（2026-10-02 审计）：同一 entry 只圆整一次——mark/measure 直读
  // 与 getEntries* 是同一对象的两条通道，各自独立圆整会叠加两份 jitter
  //（直读值 ≠ 缓冲区值，双通道不一致本身可检测）。WeakSet 标记已圆整的
  // entry，二次通道直接跳过
  var aegisRoundedEntries = new WeakSet();
  function aegisRoundEntry(entry) {{
    try {{
      if (aegisRoundedEntries.has(entry)) return entry;
      Object.defineProperty(entry, 'startTime', {{ value: reducePrecision(entry.startTime) }});
      Object.defineProperty(entry, 'duration', {{ value: reducePrecision(entry.duration) }});
      aegisRoundedEntries.add(entry);
    }} catch (e2) {{}}
    return entry;
  }}

  ['getEntries', 'getEntriesByName', 'getEntriesByType'].forEach(function(name) {{
    try {{
      var origGet = performance[name];
      var wrappedGet = function() {{
        var list = origGet.apply(this, arguments);
        try {{ for (var i = 0; i < list.length; i++) aegisRoundEntry(list[i]); }} catch (e2) {{}}
        return list;
      }};
      // RS-279：原型级 defineProperty（保留原 descriptor 形态，RS-250 口径）
      var oPG = Object.getOwnPropertyDescriptor(Performance.prototype, name);
      var tgtPG = Performance.prototype;
      if (!oPG) {{
        oPG = Object.getOwnPropertyDescriptor(performance, name);
        tgtPG = performance;
      }}
      if (oPG) {{
        Object.defineProperty(tgtPG, name, {{
          value: wrappedGet,
          writable: oPG.writable,
          enumerable: oPG.enumerable,
          configurable: oPG.configurable
        }});
      }}
      var reg = window[Symbol.for('{reg_sym}')]; if (reg) reg(wrappedGet, origGet);
    }} catch(e) {{}}
  }});

  try {{
    var origRAF = window.requestAnimationFrame;
    window.requestAnimationFrame = function(cb) {{
      if (typeof cb !== 'function') return origRAF.call(window, cb);
      return origRAF.call(window, function(ts) {{ cb(reducePrecision(ts)); }});
    }};
    var reg5 = window[Symbol.for('{reg_sym}')]; if (reg5) reg5(window.requestAnimationFrame, origRAF);
  }} catch(e) {{}}

  // RS-244（2026-10-01 审计）：Event.prototype.timeStamp——事件时间戳直取
  // 宿主内部时钟（不经 JS 可见的 performance.now），仅覆盖 now 拦不住。
  // 原型级 getter 替换（保留原 descriptor 的 enumerable/configurable——
  // 属性形态对齐原生，getOwnPropertyDescriptor 一比对齐）
  try {{
    var oTS = Object.getOwnPropertyDescriptor(Event.prototype, 'timeStamp');
    if (oTS && oTS.get) {{
      var origTS = oTS.get;
      var wrappedTS = function() {{ return reducePrecision(origTS.call(this)); }};
      Object.defineProperty(Event.prototype, 'timeStamp', {{
        get: wrappedTS,
        enumerable: oTS.enumerable,
        configurable: oTS.configurable
      }});
      var reg6 = window[Symbol.for('{reg_sym}')]; if (reg6) reg6(wrappedTS, origTS);
    }}
  }} catch(e) {{}}

  // RS-244：performance.timeOrigin——导航起点是高精度计时指纹的锚点值
  //（与 now 的差值参与指纹画像）。纯圆整不加 jitter：原生值同页恒定，
  // 加 jitter 会让两次读取不一致（自身即异常信号）。原型级优先，
  // 实例形态兜底（引擎间定义位差异）
  try {{
    var oTO = Object.getOwnPropertyDescriptor(Performance.prototype, 'timeOrigin');
    var tgtTO = Performance.prototype;
    if (!oTO) {{
      oTO = Object.getOwnPropertyDescriptor(performance, 'timeOrigin');
      tgtTO = performance;
    }}
    if (oTO && oTO.get) {{
      var origTO = oTO.get;
      var wrappedTO = function() {{
        return Math.round(origTO.call(this) / PRECISION_MS) * PRECISION_MS;
      }};
      Object.defineProperty(tgtTO, 'timeOrigin', {{
        get: wrappedTO,
        enumerable: oTO.enumerable,
        configurable: oTO.configurable
      }});
      var reg7 = window[Symbol.for('{reg_sym}')]; if (reg7) reg7(wrappedTO, origTO);
    }}
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

    // —— RS-208/216/217 回归（审计 2026-09-26） ——

    #[test]
    fn date_now_returns_integer_milliseconds() {
        // RS-208：Date.now 必须 Math.round 取整——jitter 开启时
        // reducePrecision 产出带小数，Number.isInteger(Date.now()) 一行
        // 即识破防护（Android 孪生 AD-108 同口径）
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("Math.round(reducePrecision(origDateNow()))"),
            "Date.now 通道必须取整（jitter 仅保留给 performance.now）"
        );
    }

    #[test]
    fn performance_now_descriptor_matches_native() {
        // RS-216：performance.now 覆盖的属性描述符必须对齐原生——双 false
        // 形态被 getOwnPropertyDescriptor 一查即破。
        // RS-250（2026-10-01 审计）：原型级替换 + 保留原 descriptor 的
        // writable/enumerable/configurable（实例兜底兼容引擎定义位差异）
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(Performance.prototype, 'now')"),
            "原型 descriptor 优先探测"
        );
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(performance, 'now')"),
            "实例形态兜底"
        );
        assert!(
            script.contains("writable: oPN.writable"),
            "writable 保留原生形态"
        );
        assert!(
            script.contains("enumerable: oPN.enumerable")
                && script.contains("configurable: oPN.configurable"),
            "enumerable/configurable 保留原生形态"
        );
        assert!(
            !script.contains("writable: false"),
            "脚本内不得残留 writable: false 描述符形态"
        );
    }

    #[test]
    fn get_entries_family_rounded() {
        // RS-217：getEntries/getEntriesByName/getEntriesByType 返回的条目
        // 直取宿主内部时钟——必须经实例属性遮蔽圆整 startTime/duration
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("'getEntries', 'getEntriesByName', 'getEntriesByType'"),
            "getEntries* 三入口必须全部覆盖"
        );
        assert!(
            script.contains("aegisRoundEntry(list[i])"),
            "缓冲区条目必须逐个圆整"
        );
    }

    // —— RS-244 回归（审计 2026-10-01）：timeStamp / timeOrigin 补覆盖 ——

    #[test]
    fn event_timestamp_rounded_via_prototype_getter() {
        // RS-244：Event.prototype.timeStamp 必须原型级 getter 替换——
        // 事件时间戳直取宿主内部时钟，仅覆盖 performance.now 拦不住；
        // descriptor 属性（enumerable/configurable）保留原生形态
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(Event.prototype, 'timeStamp')"),
            "timeStamp 原型 descriptor 探测"
        );
        assert!(
            script.contains("return reducePrecision(origTS.call(this));"),
            "timeStamp getter 值经 reducePrecision 圆整"
        );
        assert!(
            script.contains("enumerable: oTS.enumerable"),
            "timeStamp 覆盖保留原生 enumerable 形态"
        );
        // 注册 ToStringGuard（getter 函数对）
        assert!(script.contains("reg6(wrappedTS, origTS)"));
    }

    #[test]
    fn time_origin_rounded_without_jitter() {
        // RS-244：performance.timeOrigin 圆整——原型级优先、实例兜底；
        // 纯圆整不加 jitter（原生值同页恒定，jitter 会让双读不一致）
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(Performance.prototype, 'timeOrigin')"),
            "timeOrigin 原型 descriptor 优先探测"
        );
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(performance, 'timeOrigin')"),
            "timeOrigin 实例形态兜底（引擎定义位差异）"
        );
        assert!(
            script.contains("Math.round(origTO.call(this) / PRECISION_MS) * PRECISION_MS"),
            "timeOrigin 纯圆整（无 jitter——双读恒定）"
        );
        assert!(script.contains("reg7(wrappedTO, origTO)"));
    }

    // —— RS-278/279/296 回归（2026-10-02 审计） ——

    #[test]
    fn mark_returned_entry_rounded() {
        // RS-278：mark 返回的 entry 必须经 aegisRoundEntry 圆整——此前
        // 原样透传，startTime/duration 是宿主内部时钟的高精度原值
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("return aegisRoundEntry(origMark.call(this, name, options));"),
            "mark 返回 entry 必须圆整"
        );
    }

    #[test]
    fn mark_measure_getentries_prototype_level() {
        // RS-279：mark/measure/getEntries* 此前实例级 value 遮蔽——照
        // RS-250 口径改原型级 defineProperty（保留原 descriptor 形态）
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(Performance.prototype, 'mark')"),
            "mark 原型 descriptor 优先探测"
        );
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(Performance.prototype, 'measure')"),
            "measure 原型 descriptor 优先探测"
        );
        assert!(
            script.contains("Object.getOwnPropertyDescriptor(Performance.prototype, name)"),
            "getEntries* 原型 descriptor 优先探测"
        );
        // 实例形态兜底（引擎定义位差异）
        assert!(script.contains("Object.getOwnPropertyDescriptor(performance, 'mark')"));
        assert!(script.contains("Object.getOwnPropertyDescriptor(performance, 'measure')"));
        // 旧实例赋值遮蔽形态不得残留
        assert!(!script.contains("performance.mark ="));
        assert!(!script.contains("performance.measure ="));
        assert!(!script.contains("performance[name] = wrappedGet"));
        // descriptor 属性保留原生形态
        assert!(script.contains("writable: oPM.writable"));
        assert!(script.contains("writable: oPMe.writable"));
        assert!(script.contains("writable: oPG.writable"));
    }

    #[test]
    fn entry_rounded_once_across_channels() {
        // RS-296：同一 entry 直读与 getEntries* 双通道只圆整一次（WeakSet
        // 标记）——独立圆整会叠加两份 jitter，双通道不一致本身可检测
        let script = TimerPrecision::new().inject_script();
        assert!(
            script.contains("var aegisRoundedEntries = new WeakSet();"),
            "WeakSet 标记必须存在"
        );
        assert!(script.contains("if (aegisRoundedEntries.has(entry)) return entry;"));
        assert!(script.contains("aegisRoundedEntries.add(entry);"));
        // measure 直读通道统一走 aegisRoundEntry（单源圆整）
        assert!(
            script.contains("return aegisRoundEntry(origMeasure.call(this, name, start, end));"),
            "measure 直读与缓冲区通道必须单源"
        );
    }
}

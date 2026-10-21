
// Aegis TimerPrecision — 定时器精度降低（参照 Mullvad Browser）
// 原始策略：Mullvad VPN / Tor Project (MPL-2.0)
// 精度：1000μs，jitter：true
(function() {
  var PRECISION_US = 1000;
  var PRECISION_MS = PRECISION_US / 1000;
  var JITTER_ENABLED = true;

  function reducePrecision(value) {
    // 圆整到精度边界
    var rounded = Math.round(value / PRECISION_MS) * PRECISION_MS;
    // 添加 jitter（±50% 精度范围内的随机偏移）
    if (JITTER_ENABLED) {
      var jitterRange = PRECISION_MS / 2;
      rounded += (Math.random() - 0.5) * jitterRange;
    }
    return rounded;
  }

  // 覆盖 performance.now()
  try {
    var origPerfNow = performance.now.bind(performance);
    // R8-RS-04（第八轮）：圆整后叠加的是**无状态**随机抖动 ⇒ 相邻两次读数可回退
    //（t2 < t1），违反规范的单调非递减——回退既是一行即检的防护信号也打乱页内动画。
    var lastPerf = -Infinity;
    var wrappedPerfNow = function() {
      var v = reducePrecision(origPerfNow());
      if (v < lastPerf) v = lastPerf;
      lastPerf = v;
      return v;
    };
    // RS-216（2026-09-26 审计）：属性描述符对齐原生——双 false 形态可被
    // getOwnPropertyDescriptor 一查即破。
    // RS-250（2026-10-01 审计）：原型级替换（保留原 descriptor 属性）——
    // 此前实例 value 遮蔽可经 Performance.prototype.now.call(performance)
    // 直取原实现。原型 descriptor 优先，实例形态兜底（引擎定义位差异）
    var oPN = Object.getOwnPropertyDescriptor(Performance.prototype, 'now');
    var tgtPN = Performance.prototype;
    if (!oPN) {
      oPN = Object.getOwnPropertyDescriptor(performance, 'now');
      tgtPN = performance;
    }
    if (oPN) {
      Object.defineProperty(tgtPN, 'now', {
        value: wrappedPerfNow,
        writable: oPN.writable,
        enumerable: oPN.enumerable,
        configurable: oPN.configurable
      });
    }
    var reg1 = window[Symbol.for('proxy.register.v1')]; if (reg1) reg1(wrappedPerfNow, origPerfNow);
  } catch(e) {}

  // 覆盖 Date.now()
  // RS-208（2026-09-26 审计）：Math.round 取整——jitter 开启时
  // reducePrecision 返回带小数（±50% 精度随机偏移），原生 Date.now 恒为
  // 整数毫秒，Number.isInteger(Date.now()) 一行即识破防护。jitter 仅保留
  // 给 performance.now（Android 孪生 AD-108 同口径）
  try {
    var origDateNow = Date.now;
    Date.now = function() { return Math.round(reducePrecision(origDateNow())); };
    var reg2 = window[Symbol.for('proxy.register.v1')]; if (reg2) reg2(Date.now, origDateNow);
  } catch(e) {}

  // RS-074（审计 2026-09-25）：mark/measure/timeStamp 的 startTime 与
  // duration 不经 JS 可见的 performance.now——宿主内部时钟直取，仅覆盖
  // now 属性拦不住这条路径，必须独立圆整
  try {
    var origMark = performance.mark;
    // RS-278（2026-10-02 审计）：mark 返回的 entry 此前原样透传——
    // startTime 经宿主内部时钟（绕过 JS 可见的 performance.now），
    // entry 的 startTime/duration 是高精度原值。返回前统一走
    // aegisRoundEntry 圆整（RS-296：WeakSet 保证双通道只圆整一次）
    var wrappedMark = function(name, options) {
      if (options && typeof options.startTime === 'number') {
        options = Object.assign({}, options, { startTime: reducePrecision(options.startTime) });
      }
      return aegisRoundEntry(origMark.call(this, name, options));
    };
    // RS-279（2026-10-02 审计）：原型级 defineProperty（保留原 descriptor
    // 形态）——照 RS-250 now/timeOrigin 口径。此前实例 value 遮蔽可经
    // Performance.prototype.mark.call(performance, ...) 直取原实现
    var oPM = Object.getOwnPropertyDescriptor(Performance.prototype, 'mark');
    var tgtPM = Performance.prototype;
    if (!oPM) {
      oPM = Object.getOwnPropertyDescriptor(performance, 'mark');
      tgtPM = performance;
    }
    if (oPM) {
      Object.defineProperty(tgtPM, 'mark', {
        value: wrappedMark,
        writable: oPM.writable,
        enumerable: oPM.enumerable,
        configurable: oPM.configurable
      });
    }
    var reg3 = window[Symbol.for('proxy.register.v1')]; if (reg3) reg3(wrappedMark, origMark);
  } catch(e) {}

  try {
    var origMeasure = performance.measure;
    // RS-296（2026-10-02 审计）：measure 直读与 getEntries* 缓冲区读取是
    // 同一 entry 对象的两条通道——统一走 aegisRoundEntry 单源圆整
    //（WeakSet 标记单次，独立圆整会叠加两份 jitter，双通道不一致可检测）
    var wrappedMeasure = function(name, start, end) {
      return aegisRoundEntry(origMeasure.call(this, name, start, end));
    };
    // RS-279：原型级 defineProperty（保留原 descriptor 形态，RS-250 口径）
    var oPMe = Object.getOwnPropertyDescriptor(Performance.prototype, 'measure');
    var tgtPMe = Performance.prototype;
    if (!oPMe) {
      oPMe = Object.getOwnPropertyDescriptor(performance, 'measure');
      tgtPMe = performance;
    }
    if (oPMe) {
      Object.defineProperty(tgtPMe, 'measure', {
        value: wrappedMeasure,
        writable: oPMe.writable,
        enumerable: oPMe.enumerable,
        configurable: oPMe.configurable
      });
    }
    var reg4 = window[Symbol.for('proxy.register.v1')]; if (reg4) reg4(wrappedMeasure, origMeasure);
  } catch(e) {}

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
  function aegisRoundEntry(entry) {
    try {
      if (aegisRoundedEntries.has(entry)) return entry;
      Object.defineProperty(entry, 'startTime', { value: reducePrecision(entry.startTime) });
      Object.defineProperty(entry, 'duration', { value: reducePrecision(entry.duration) });
      aegisRoundedEntries.add(entry);
    } catch (e2) {}
    return entry;
  }

  ['getEntries', 'getEntriesByName', 'getEntriesByType'].forEach(function(name) {
    try {
      var origGet = performance[name];
      var wrappedGet = function() {
        var list = origGet.apply(this, arguments);
        try { for (var i = 0; i < list.length; i++) aegisRoundEntry(list[i]); } catch (e2) {}
        return list;
      };
      // RS-279：原型级 defineProperty（保留原 descriptor 形态，RS-250 口径）
      var oPG = Object.getOwnPropertyDescriptor(Performance.prototype, name);
      var tgtPG = Performance.prototype;
      if (!oPG) {
        oPG = Object.getOwnPropertyDescriptor(performance, name);
        tgtPG = performance;
      }
      if (oPG) {
        Object.defineProperty(tgtPG, name, {
          value: wrappedGet,
          writable: oPG.writable,
          enumerable: oPG.enumerable,
          configurable: oPG.configurable
        });
      }
      var reg = window[Symbol.for('proxy.register.v1')]; if (reg) reg(wrappedGet, origGet);
    } catch(e) {}
  });

  try {
    var origRAF = window.requestAnimationFrame;
    window.requestAnimationFrame = function(cb) {
      if (typeof cb !== 'function') return origRAF.call(window, cb);
      return origRAF.call(window, function(ts) { cb(reducePrecision(ts)); });
    };
    var reg5 = window[Symbol.for('proxy.register.v1')]; if (reg5) reg5(window.requestAnimationFrame, origRAF);
  } catch(e) {}

  // RS-244（2026-10-01 审计）：Event.prototype.timeStamp——事件时间戳直取
  // 宿主内部时钟（不经 JS 可见的 performance.now），仅覆盖 now 拦不住。
  // 原型级 getter 替换（保留原 descriptor 的 enumerable/configurable——
  // 属性形态对齐原生，getOwnPropertyDescriptor 一比对齐）
  try {
    var oTS = Object.getOwnPropertyDescriptor(Event.prototype, 'timeStamp');
    if (oTS && oTS.get) {
      var origTS = oTS.get;
      var wrappedTS = function() { return reducePrecision(origTS.call(this)); };
      Object.defineProperty(Event.prototype, 'timeStamp', {
        get: wrappedTS,
        enumerable: oTS.enumerable,
        configurable: oTS.configurable
      });
      var reg6 = window[Symbol.for('proxy.register.v1')]; if (reg6) reg6(wrappedTS, origTS);
    }
  } catch(e) {}

  // RS-244：performance.timeOrigin——导航起点是高精度计时指纹的锚点值
  //（与 now 的差值参与指纹画像）。纯圆整不加 jitter：原生值同页恒定，
  // 加 jitter 会让两次读取不一致（自身即异常信号）。原型级优先，
  // 实例形态兜底（引擎间定义位差异）
  try {
    var oTO = Object.getOwnPropertyDescriptor(Performance.prototype, 'timeOrigin');
    var tgtTO = Performance.prototype;
    if (!oTO) {
      oTO = Object.getOwnPropertyDescriptor(performance, 'timeOrigin');
      tgtTO = performance;
    }
    if (oTO && oTO.get) {
      var origTO = oTO.get;
      var wrappedTO = function() {
        return Math.round(origTO.call(this) / PRECISION_MS) * PRECISION_MS;
      };
      Object.defineProperty(tgtTO, 'timeOrigin', {
        get: wrappedTO,
        enumerable: oTO.enumerable,
        configurable: oTO.configurable
      });
      var reg7 = window[Symbol.for('proxy.register.v1')]; if (reg7) reg7(wrappedTO, origTO);
    }
  } catch(e) {}
})();


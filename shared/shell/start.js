// start.js —— 跨端宿主桥适配层（ADR-007 单源首页）
// 从 start.html 内联块外置（审计 I83：内联脚本依赖"受信壳页"假设——
// CSP script-src 'self' 后内联不可执行，全部脚本走外部文件）。
// ================= 跨端宿主桥适配层（ADR-007 单源首页） =================
// Android：AegisBridge（@JavascriptInterface，同步返回——由适配层统一包装
// 成 thenable）；Windows C#（ADR-009 正典栈）：WebView2 postMessage 桥
//（ntp.aegis.local 受信虚拟主机——远程页面上 WebMessage 被宿主按来源
// 关闭，本桥不可达）。
// WB-114（2026-09-26 审计）：已归档 pywebview 栈的 'win' 桥分支整支删除——
// 正典发布不含该桥，纯死代码面；Host 收敛 cs/android 双端
//（kind() 判定优先级 android > cs，全无则 null）。
// 能力面差异：Android 首页当前能力 = 错误上报/引擎/导航/壁纸/画板；
// 书签宫格、导入向导、会话恢复为 Windows 能力（Android 上自动隐藏）。
// WB-057（审计 2026-09-23 清单·W5 批）：首页跨文件时序常量单源——此前
// 200ms/1200ms/15000ms 魔法延时散落 start.main.js 与 start.import.js。
// 消费方统一读 window.AegisTiming（本文件最先加载——WB-125 顺序契约），
// 读取端保留字面量兜底以兼容无头测试的分文件加载形态。
var AegisTiming = {
  BOOKMARK_RETRY_MS: 200,          // 书签渲染：桥未就绪重试间隔
  BOOKMARK_RETRY_MAX: 10,          // 书签渲染：有界重试次数上限
  SEARCH_BUSY_RESET_MS: 1200,      // 搜索按钮「搜索中…」防重放锁复位延时
  IMPORT_SCAN_TIMEOUT_MS: 15000,   // 导入向导：扫描超时兜底
  IMPORT_RUN_TIMEOUT_MS: 60000     // 导入向导：执行总超时兜底（WB-135，
                                    // 2026-10-01 审计——桥挂起时 running 态
                                    // 不再永久卡死向导）
};
if (typeof window !== 'undefined') { window.AegisTiming = AegisTiming; }

var Host = (function () {
  var andApi = function () { return window.AegisBridge || null; };
  var csApi = function () {
    return (window.chrome && chrome.webview && chrome.webview.postMessage) ? chrome.webview : null;
  };
  // C# 桥请求通道：postMessage 关联 id + 单一 message 监听分发响应
  var _csSeq = 0, _csPending = {}, _csListening = false;
  // WB-037（审计 2026-09-23 清单·W5 批）：pending 此前无 TTL 上限——宿主
  // 永不回包时回调条目泄漏（页面生命周期内只增不减）。惰性清扫实现 TTL：
  // 每次新请求前清理超龄条目（以 cb(null) 兜底完成），不引入定时器——
  // 保持「零定时器零 IO、未决回调不持有事件循环」的既有设计性质
  //（WB-128 回归锁），并避免 setTimeout TTL 在无头测试中拖住进程退出。
  var CS_CALL_TTL_MS = 30000;
  function sweepStalePending(now) {
    for (var k in _csPending) {
      if (now - _csPending[k].ts > CS_CALL_TTL_MS) {
        var f = _csPending[k].cb; delete _csPending[k];
        try { f(null); } catch (err) { try { Host.jsError('ntp callback: ' + err); } catch (e2) {} }
      }
    }
  }
  function csCall(op, args, cb) {
    var w = csApi(); if (!w) { if (cb) cb(null); return; }
    if (!_csListening) {
      _csListening = true;
      w.addEventListener('message', function (e) {
        var d = e.data;
        if (d && d.__aegisRes && _csPending[d.id]) {
          var f = _csPending[d.id].cb; delete _csPending[d.id];
          try { f(d.result); } catch (err) { try { Host.jsError('ntp callback: ' + err); } catch (e2) {} }
        }
      });
    }
    sweepStalePending(Date.now());
    var id = ++_csSeq;
    _csPending[id] = { cb: cb || function () {}, ts: Date.now() };
    w.postMessage({ __aegis: 1, id: id, op: op, args: args || [] });
  }
  return {
    kind: function () { return andApi() ? 'android' : (csApi() ? 'cs' : null); },
    has: function (feat) {
      var k = this.kind();
      if (!k) return false;
      if (k === 'cs') return true;
      var androidFeats = { engine: 1, navigate: 1, wallpaper: 1, geo: 1, snake: 1 };
      return !!androidFeats[feat];
    },
    jsError: function () {
      var a = andApi(); if (a) { a.logError([].slice.call(arguments).join(' | ')); return; }
      var c = csApi(); if (c) csCall('jsError', [].slice.call(arguments));
    },
    setEngine: function (key) {
      var a = andApi(); if (a) { a.setEngine(key); return; }
      csCall('setEngine', [key]);
    },
    getEngine: function (cb) {
      // P1-2 修复（搜索审计 2026-09-01）：Android 桥返回 JSON 字符串
      //（与旧 Windows get_search_engine 同构）——旧实现直接回传 key 字符串，
      // data.engines 为 undefined → ENGINES=[] → 引擎 pill 点击无响应
      var a = andApi(); if (a) {
        // P2 修复（全量复审 2026-09-01）：解析失败/空结构不再静默 cb(null)
        //（引擎胶囊无响应）——回退默认引擎集（与 Android
        // SearchEngines.ENGINE_URLS 同构），胶囊保持可用
        function engineFallback() {
          return { engine: 'baidu', engines: [
            { key: 'baidu', name: '百度' },
            { key: 'bing', name: '必应' },
            { key: 'google', name: '谷歌' },
            { key: 'sogou', name: '搜狗' }
          ]};
        }
        try {
          var parsed = JSON.parse(a.getEngine());
          cb(parsed && parsed.engines && parsed.engines.length ? parsed : engineFallback());
        } catch (e) {
          cb(engineFallback());
        }
        return;
      }
      csCall('getEngine', [], cb);
    },
    navigate: function (url) {
      var a = andApi(); if (a) { a.navigate(url); return; }
      csCall('navigate', [url]);
    },
    goBack: function () {
      var a = andApi(); if (a) { a.goBack(); return; }
      csCall('goBack', []);
    },
    setWallpaper: function (name) {
      var a = andApi(); if (a) { a.setWallpaper(name); return; }
      csCall('setWallpaper', [name]);
    },
    getWallpaper: function (cb) {
      var a = andApi(); if (a) { cb(a.getWallpaper()); return; }
      csCall('getWallpaper', [], cb);
    },
    openGeo: function (onFail) {
      var a = andApi(); if (a) { if (!a.openGeogebra()) onFail(); return; }
      csCall('openGeo', [], function (ok) { if (!ok) onFail(); });
    },
    hasSaved: function (cb) {
      if (andApi()) { cb(0); return; }  // Android：会话恢复为 Windows 能力
      csCall('hasSaved', [], cb);
    },
    restoreSession: function () {
      csCall('restoreSession', []);
    },
    bookmarks: function (cb) {
      // Android：书签宫格为 Windows 能力（has('bookmarks')=false 时调用方
      // 已提前返回）——本分支是纵深防御：调用方漏检能力面时返回空集
      // 而不是把 undefined 传进渲染器（WB-014：保留并注明，勿删）
      if (andApi()) { cb([]); return; }
      csCall('bookmarks', [], cb);
    },
    importScan: function (cb) {
      // Android：导入向导为 Windows 能力（同 bookmarks——纵深防御分支）
      if (andApi()) { cb([]); return; }
      csCall('importScan', [], cb);
    },
    importBookmarks: function (src, cb) {
      // 返回 Promise——导入向导 runImport 以返回值收集统计（WB-001：此前
      // 适配层分支返回 undefined，cs 端结果只进回调，导入统计恒 0/0）
      if (andApi()) { return Promise.resolve({ imported: 0, total: 0 }); }
      return new Promise(function (resolve) { csCall('importBookmarks', [src], resolve); });
    },
    importHistory: function (limit, src, cb) {
      if (andApi()) { return Promise.resolve({ imported: 0, total: 0 }); }
      return new Promise(function (resolve) { csCall('importHistory', [limit, src], resolve); });
    },
  };
})();

// WB-140（2026-10-01 审计）：error/unhandledrejection 监听从 start.main.js
//（四文件中最末加载）前移至首文件——此前 start.snake.js/start.import.js/
// start.main.js 三个文件的顶层异常发生在监听注册前，零上报。本文件最先
// 加载（WB-125 顺序契约），此处注册后全程覆盖。jsError 自身再失败则放弃
//（防上报通道异常递归）。window.addEventListener 存在性守卫兼容无头测试
// 的裸 window 桩（helpers.mjs loadHost 注入普通对象）。
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('error', function (e) {
    try {
      Host.jsError(
        e.message || 'unknown', e.filename || '', e.lineno, e.colno,
        (e.error && e.error.stack) || '');
    } catch (err) {}
  });
  window.addEventListener('unhandledrejection', function (e) {
    try {
      Host.jsError(
        'Promise rejection: ' + (e.reason || ''), '', 0, 0,
        (e.reason && e.reason.stack) || '');
    } catch (err) {}
  });
}

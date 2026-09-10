// start.js —— 跨端宿主桥适配层（ADR-007 单源首页）
// 从 start.html 内联块外置（审计 I83：内联脚本依赖"受信壳页"假设——
// CSP script-src 'self' 后内联不可执行，全部脚本走外部文件）。
// ================= 跨端宿主桥适配层（ADR-007 单源首页） =================
// Windows：pywebview.api（异步 Promise）；Android：AegisBridge
// （@JavascriptInterface，同步返回——由适配层统一包装成 thenable）；
// Windows C#（ADR-009 正典栈）：WebView2 postMessage 桥（ntp.aegis.local
// 受信虚拟主机——远程页面上 WebMessage 被宿主按来源关闭，本桥不可达）。
// 能力面差异：Android 首页当前能力 = 错误上报/引擎/导航/壁纸/画板；
// 书签宫格、导入向导、会话恢复为 Windows 能力（Android 上自动隐藏）。
var Host = (function () {
  var winApi = function () { return (window.pywebview && pywebview.api) || null; };
  var andApi = function () { return window.AegisBridge || null; };
  var csApi = function () {
    return (window.chrome && chrome.webview && chrome.webview.postMessage) ? chrome.webview : null;
  };
  // C# 桥请求通道：postMessage 关联 id + 单一 message 监听分发响应
  var _csSeq = 0, _csPending = {}, _csListening = false;
  function csCall(op, args, cb) {
    var w = csApi(); if (!w) { if (cb) cb(null); return; }
    if (!_csListening) {
      _csListening = true;
      w.addEventListener('message', function (e) {
        var d = e.data;
        if (d && d.__aegisRes && _csPending[d.id]) {
          var f = _csPending[d.id]; delete _csPending[d.id];
          try { f(d.result); } catch (err) { try { Host.jsError('ntp callback: ' + err); } catch (e2) {} }
        }
      });
    }
    var id = ++_csSeq;
    _csPending[id] = cb || function () {};
    w.postMessage({ __aegis: 1, id: id, op: op, args: args || [] });
  }
  return {
    kind: function () { return winApi() ? 'win' : (andApi() ? 'android' : (csApi() ? 'cs' : null)); },
    has: function (feat) {
      var k = this.kind();
      if (!k) return false;
      if (k === 'win' || k === 'cs') return true;
      var androidFeats = { engine: 1, navigate: 1, wallpaper: 1, geo: 1, snake: 1 };
      return !!androidFeats[feat];
    },
    jsError: function () {
      var w = winApi(); if (w) { w.js_error.apply(w, arguments); return; }
      var a = andApi(); if (a) { a.logError([].slice.call(arguments).join(' | ')); return; }
      var c = csApi(); if (c) csCall('jsError', [].slice.call(arguments));
    },
    setEngine: function (key) {
      var w = winApi(); if (w) { w.set_search_engine(key); return; }
      var a = andApi(); if (a) { a.setEngine(key); return; }
      csCall('setEngine', [key]);
    },
    getEngine: function (cb) {
      var w = winApi(); if (w) { w.get_search_engine().then(cb); return; }
      // P1-2 修复（搜索审计 2026-09-01）：Android 桥返回 JSON 字符串
      //（与 Windows get_search_engine 同构）——旧实现直接回传 key 字符串，
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
      var w = winApi(); if (w) { w.navigate(url); return; }
      var a = andApi(); if (a) { a.navigate(url); return; }
      csCall('navigate', [url]);
    },
    goBack: function () {
      var w = winApi(); if (w) { w.go_back(); return; }
      var a = andApi(); if (a) { a.goBack(); return; }
      csCall('goBack', []);
    },
    setWallpaper: function (name) {
      var w = winApi(); if (w) { w.set_wallpaper(name); return; }
      var a = andApi(); if (a) { a.setWallpaper(name); return; }
      csCall('setWallpaper', [name]);
    },
    getWallpaper: function (cb) {
      var w = winApi(); if (w) { w.get_wallpaper().then(cb); return; }
      var a = andApi(); if (a) { cb(a.getWallpaper()); return; }
      csCall('getWallpaper', [], cb);
    },
    openGeo: function (onFail) {
      var w = winApi();
      if (w) { w.open_geogebra().then(function (ok) { if (!ok) onFail(); }); return; }
      var a = andApi(); if (a) { if (!a.openGeogebra()) onFail(); return; }
      csCall('openGeo', [], function (ok) { if (!ok) onFail(); });
    },
    hasSaved: function (cb) {
      var w = winApi(); if (w) { w.has_saved_session().then(cb); return; }
      if (andApi()) { cb(0); return; }  // Android：会话恢复为 Windows 能力
      csCall('hasSaved', [], cb);
    },
    restoreSession: function () {
      var w = winApi(); if (w) { w.restore_session(); return; }
      csCall('restoreSession', []);
    },
    bookmarks: function (cb) {
      var w = winApi(); if (w) { w.get_bookmarks().then(cb); return; }
      if (andApi()) { cb([]); return; }  // Android：书签宫格暂无数据源
      csCall('bookmarks', [], cb);
    },
    importScan: function (cb) {
      var w = winApi(); if (w) { w.scan_import_sources().then(cb); return; }
      if (andApi()) { cb([]); return; }  // Android：导入向导为 Windows 能力
      csCall('importScan', [], cb);
    },
    importBookmarks: function (src, cb) {
      var w = winApi(); if (w) { w.import_bookmarks(src).then(cb); return; }
      if (andApi()) { cb({ imported: 0, total: 0 }); return; }
      csCall('importBookmarks', [src], cb);
    },
    importHistory: function (limit, src, cb) {
      var w = winApi(); if (w) { w.import_history(limit, src).then(cb); return; }
      if (andApi()) { cb({ imported: 0, total: 0 }); return; }
      csCall('importHistory', [limit, src], cb);
    },
  };
})();

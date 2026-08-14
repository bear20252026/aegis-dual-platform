"""shell_toolbar.py —— 注入式工具栏脚本（单文件单职责）。

职责：提供 Aegis 浏览器每一页顶部的注入式工具栏（标签条 / 导航按钮 /
地址栏 / JS 错误上报）的完整 JS 脚本。本文件只做两件事：
  1. 持有 TOOLBAR_JS 静态脚本（原样迁移自 main_webview.py）；
  2. 提供 build_toolbar_js()：把当前 URL 与标签快照注入占位符，返回可
     直接 evaluate 的完整脚本。

设计要点：
- TOOLBAR_JS 是纯 JS 字符串，不含任何 Python 逻辑；
- 占位符 __AEGIS_URL__ / __TABS_JSON__ 由 build_toolbar_js() 用
  json.dumps 注入（值永远是合法 JSON，杜绝 JS 注入）；
- 整个 IIFE 自带 try/catch：任何页面（含 CSP 严格站点、无 body 的
  空白页）都不允许因注入脚本抛错而中断页面。
"""

import json

# R1 借鉴 min 的 defaultKeybindings/keybindings 分离：
# 默认快捷键表独立为常量（单一来源），用户可在 config 中覆盖
# （build_toolbar_js 注入生效的映射，TOOLBAR_JS 不再硬编码按键）。
DEFAULT_KEYBINDINGS: dict[str, str] = {
    "new_tab": "t",      # Ctrl/Meta + T → 新标签
    "close_tab": "w",    # Ctrl/Meta + W → 关闭当前标签
    "focus_url": "l",    # Ctrl/Meta + L → 聚焦地址栏
}

# 注入式工具栏：单行紧凑设计（苹果风格）。
# - 高度 40px，毛玻璃半透明深蓝紫（与 aurora 壁纸同色系），白色文字
# - 左侧标签条（紧凑胶囊）+ 新建标签 + 后退/前进/刷新/主页 + 地址栏
# Python 侧把标签数据（__TABS_JSON__）与当前网址（__AEGIS_URL__）
# 直接内嵌进脚本，一次 evaluate 完成渲染 —— 零 HTTP 往返。
TOOLBAR_JS = r"""
(function () {
  function bootUI() {
  try {
    if (document.getElementById('aegis-chrome')) return;
    var TABS_DATA = __TABS_JSON__;
    var bar = document.createElement('div');
    bar.id = 'aegis-chrome';
    bar.style.cssText = [
      'position:fixed','top:0','left:0','right:0','height:40px','z-index:2147483647',
      'display:flex','align-items:center','gap:4px','padding:0 8px',
      'background:linear-gradient(180deg,rgba(40,34,78,0.86),rgba(28,24,62,0.84))',
      'backdrop-filter:blur(16px) saturate(150%)',
      '-webkit-backdrop-filter:blur(16px) saturate(150%)',
      'border-bottom:1px solid rgba(255,255,255,0.14)',
      'box-shadow:0 2px 12px rgba(15,10,40,0.35)','box-sizing:border-box',
      'font-family:' + (__FONT_FAMILY__ || 'Inter,"Source Han Sans SC",system-ui,-apple-system,"Segoe UI",sans-serif')
    ].join(';');

    // —— 标签条（紧凑胶囊，限宽省略）——
    var tabsWrap = document.createElement('div');
    tabsWrap.style.cssText = 'display:flex;align-items:center;gap:3px;height:28px;' +
      'overflow:hidden;flex:0 1 auto;min-width:0;max-width:55%;';
    bar.appendChild(tabsWrap);

    var tabs = (TABS_DATA && TABS_DATA.tabs) || [];
    var cur = (TABS_DATA && TABS_DATA.current) || 0;
    for (var i = 0; i < tabs.length; i++) {
      (function (idx) {
        var t = document.createElement('div');
        t.style.cssText = 'display:inline-flex;align-items:center;gap:4px;max-width:120px;height:26px;' +
          'padding:0 4px 0 10px;border-radius:7px;cursor:pointer;font-size:11px;color:rgba(255,255,255,0.72);' +
          'background:' + (idx === cur ? 'rgba(255,255,255,0.18)' : 'transparent') + ';' +
          'border:1px solid ' + (idx === cur ? 'rgba(255,255,255,0.22)' : 'transparent') + ';';
        var label = document.createElement('span');
        var isPin = !!(tabs[idx] && tabs[idx].pinned);
        label.textContent = (isPin ? '\u{1F4CC} ' : '') + ((tabs[idx] && tabs[idx].title) || '新标签页');
        label.title = isPin ? '固定标签（右键取消固定）' : '';
        label.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff;';
        var x = document.createElement('span');
        x.textContent = '\u00d7';
        x.style.cssText = 'width:15px;height:15px;line-height:13px;text-align:center;border-radius:50%;' +
          'cursor:pointer;color:rgba(255,255,255,0.65);font-size:12px;flex:0 0 auto;';
        x.onmouseenter = function(){ x.style.background = 'rgba(255,255,255,0.25)'; };
        x.onmouseleave = function(){ x.style.background = 'transparent'; };
        x.onclick = function (e) {
          e.stopPropagation();
          try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
        };
        t.appendChild(label);
        t.appendChild(x);
        t.onclick = function () {
          if (idx !== cur && window.pywebview && pywebview.api) {
            try { pywebview.api.switch_tab(idx); } catch (err) {}
          }
        };
        // 中键（button===1）关闭标签；preventDefault 阻止 WebView 中键自动滚动
        t.onauxclick = function (e) {
          if (e.button !== 1) return;
          e.preventDefault();
          try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
        };
        tabsWrap.appendChild(t);
      })(i);
    }
    var nb = document.createElement('div');
    nb.textContent = '+';
    nb.title = '新标签页';
    nb.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;' +
      'width:24px;height:24px;border-radius:7px;cursor:pointer;color:rgba(255,255,255,0.8);font-size:15px;' +
      'flex:0 0 auto;';
    nb.onmouseenter = function(){ nb.style.background = 'rgba(255,255,255,0.16)'; };
    nb.onmouseleave = function(){ nb.style.background = 'transparent'; };
    nb.onclick = function () {
      try { if (window.pywebview && pywebview.api) pywebview.api.new_tab(); } catch (err) {}
    };
    tabsWrap.appendChild(nb);

    // —— 导航按钮 ——
    function btn(glyph, title, act) {
      var b = document.createElement('button');
      b.textContent = glyph; b.title = title;
      b.style.cssText = 'width:26px;height:26px;border:0;background:transparent;border-radius:7px;' +
        'font-size:13px;cursor:pointer;color:rgba(255,255,255,0.85);flex:0 0 auto;line-height:1;';
      b.onmouseenter = function(){ b.style.background = 'rgba(255,255,255,0.16)'; };
      b.onmouseleave = function(){ b.style.background = 'transparent'; };
      b.onclick = function(){
        try { if (window.pywebview && pywebview.api) pywebview.api[act](); } catch (e) {}
      };
      bar.appendChild(b);
      return b;
    }
    btn('\u2190', '后退', 'go_back');
    btn('\u2192', '前进', 'go_forward');
    btn('\u21bb', '刷新', 'reload_page');
    btn('\u2302', '主页', 'go_home');

    // —— 地址栏 ——
    var inp = document.createElement('input');
    inp.id = 'aegis-url';
    inp.spellcheck = false;
    inp.value = '__AEGIS_URL__';
    inp.style.cssText = 'flex:1;min-width:0;height:28px;border:1px solid rgba(255,255,255,0.18);' +
      'border-radius:14px;padding:0 12px;font-size:12px;outline:none;' +
      'background:rgba(255,255,255,0.14);color:#fff;';
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && window.pywebview && pywebview.api) {
        try { pywebview.api.navigate(inp.value); } catch (err) {}
      }
    });
    bar.appendChild(inp);

    // —— 落地 C：全文搜索历史联想（借鉴 min searchbar placeSuggestions）——
    // 输入防抖 250ms 后调用 search_history_fulltext（js_api 异步 Promise）；
    // 结果下拉固定定位在地址栏下方；点击联想项导航；Esc/失焦关闭。
    // 安全：结果一律用 textContent 渲染（杜绝 HTML 注入）；失败静默。
    var suggWrap = document.createElement('div');
    suggWrap.id = 'aegis-suggest';
    suggWrap.style.cssText = 'position:fixed;top:40px;left:0;right:0;display:none;' +
      'background:rgba(28,24,62,0.96);border-bottom:1px solid rgba(255,255,255,0.14);' +
      'box-shadow:0 4px 16px rgba(15,10,40,0.4);z-index:2147483646;max-height:320px;' +
      'overflow-y:auto;font-size:12px;color:#fff;';
    document.documentElement.appendChild(suggWrap);
    var suggTimer = null;
    function closeSuggest() { suggWrap.style.display = 'none'; }
    // 影子字段接入：search_suggestions 开关（__SEARCH_SUGGEST__ 注入
    // true/false 布尔字面量；关闭时完全禁用联想，回车导航不受影响）
    var suggestEnabled = __SEARCH_SUGGEST__;
    inp.addEventListener('input', function () {
      if (suggTimer) clearTimeout(suggTimer);
      if (!suggestEnabled) { closeSuggest(); return; }
      var v = inp.value.trim();
      if (v.length < 2) { closeSuggest(); return; }  // 短输入不搜索
      suggTimer = setTimeout(function () {
        try {
          if (!(window.pywebview && pywebview.api && pywebview.api.search_history_fulltext)) return;
          pywebview.api.search_history_fulltext(v, 8).then(function (items) {
            if (!(items && items.length)) { closeSuggest(); return; }
            suggWrap.textContent = '';
            for (var i = 0; i < items.length; i++) {
              (function (it) {
                var row = document.createElement('div');
                row.style.cssText = 'display:flex;align-items:center;gap:8px;' +
                  'padding:6px 12px;cursor:pointer;';
                row.onmouseenter = function(){ row.style.background = 'rgba(255,255,255,0.10)'; };
                row.onmouseleave = function(){ row.style.background = 'transparent'; };
                var t = document.createElement('span');
                t.textContent = (it.title || it.url || '');
                t.style.cssText = 'flex:0 1 45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                var u = document.createElement('span');
                u.textContent = (it.url || '');
                u.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;' +
                  'white-space:nowrap;color:rgba(255,255,255,0.6);';
                row.appendChild(t); row.appendChild(u);
                row.onclick = function () {
                  closeSuggest();
                  try { if (window.pywebview && pywebview.api) pywebview.api.navigate(it.url); } catch (e2) {}
                };
                suggWrap.appendChild(row);
              })(items[i]);
            }
            suggWrap.style.display = 'block';
          }).catch(function () { closeSuggest(); });
        } catch (e3) { closeSuggest(); }
      }, 250);
    });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeSuggest();
    });

    var root = document.documentElement || document;
    root.appendChild(bar);
    if (document.body) document.body.style.marginTop = '40px';

    // —— JS 错误上报：页面任何 JS 异常 → Python 日志（后台静默）——
    if (window.pywebview && pywebview.api && !window.__aegis_err_hooked) {
      window.__aegis_err_hooked = true;
      window.addEventListener('error', function (e) {
        try {
          pywebview.api.js_error(
            e.message || 'unknown', e.filename || '', e.lineno, e.colno,
            (e.error && e.error.stack) || ''
          );
        } catch (err) {}
      });
      window.addEventListener('unhandledrejection', function (e) {
        try {
          pywebview.api.js_error(
            'Promise rejection: ' + (e.reason || ''), '', 0, 0,
            (e.reason && e.reason.stack) || ''
          );
        } catch (err) {}
      });
    }

    // —— 快捷键（一次绑定；按键表由 __KEYBINDINGS_JSON__ 注入，
    //    默认来自 DEFAULT_KEYBINDINGS，用户可在 config 覆盖）——
    if (window.pywebview && pywebview.api && !window.__aegis_keys_hooked) {
      window.__aegis_keys_hooked = true;
      var KB = __KEYBINDINGS_JSON__ || {};
      window.addEventListener('keydown', function (e) {
        try {
          if (!(e.ctrlKey || e.metaKey)) return;
          var k = (e.key || '').toLowerCase();
          if (KB.new_tab && k === KB.new_tab) {
            e.preventDefault();
            pywebview.api.new_tab();
          } else if (KB.close_tab && k === KB.close_tab) {
            e.preventDefault();
            var ci = (TABS_DATA && TABS_DATA.current) || 0;
            pywebview.api.close_tab(ci);
          } else if (KB.focus_url && k === KB.focus_url) {
            e.preventDefault();
            var urlInput = document.getElementById('aegis-url');
            if (urlInput) { urlInput.focus(); urlInput.select(); }
          }
        } catch (err) {}
      });
    }
  } catch (e) { /* 注入失败绝不影响页面本身 */ }
  }

  // 双保险初始化（方向②-P1）：pywebview.api 不保证在 onload 可用，
  // 官方建议订阅 pywebviewready（js_api 完全注入后触发）。
  // 三重保险：①立即尝试（api 可能已就绪）②pywebviewready 事件
  // ③setTimeout 兜底（防 React/Vite 等错过事件，issue #1290）。
  var _booted = false;
  function _tryBoot() {
    if (_booted) return;
    if (window.pywebview && window.pywebview.api) {
      _booted = true;
      bootUI();
    }
  }
  window.addEventListener('pywebviewready', _tryBoot);
  _tryBoot();
  setTimeout(_tryBoot, 150);
})();
"""

# 左侧垂直标签栏（tabs_position="left" 时由 build_toolbar_js 追加注入）。
# 独立 IIFE：读取 TOOLBAR_JS 已注入的 TABS_DATA，复用其 JS 桥调用；
# 与顶部标签条并存 —— 顶部条保留导航/地址栏，垂直栏专职标签切换。
# 布局：固定左侧 200px 栏，标签竖排；失败静默（回退纯顶部布局）。
VERTICAL_TABS_JS = r"""
(function () {
  try {
    if (document.getElementById('aegis-vtabs')) return;
    if (document.getElementById('aegis-chrome')) {
      document.body.style.marginLeft = '200px';
    }
    var V = document.createElement('div');
    V.id = 'aegis-vtabs';
    V.style.cssText = 'position:fixed;top:40px;left:0;bottom:0;width:200px;' +
      'overflow-y:auto;background:rgba(24,20,48,0.92);' +
      'border-right:1px solid rgba(255,255,255,0.10);' +
      'z-index:2147483646;box-sizing:border-box;padding:6px 4px;';
    var data = window.__aegis_vtabs_data || {};
    var tabs = (data && data.tabs) || [];
    var cur = (data && data.current) || 0;
    function mkTab(idx) {
      var t = document.createElement('div');
      t.style.cssText = 'display:flex;align-items:center;gap:4px;height:30px;' +
        'padding:0 6px;border-radius:6px;cursor:pointer;font-size:12px;' +
        'color:rgba(255,255,255,0.85);margin-bottom:2px;' +
        'background:' + (idx === cur ? 'rgba(255,255,255,0.16)' : 'transparent') + ';';
      var label = document.createElement('span');
      var tp = (tabs[idx] && tabs[idx].pinned) ? '\u{1F4CC} ' : '';
      label.textContent = tp + ((tabs[idx] && tabs[idx].title) || '新标签页');
      label.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;' +
        'white-space:nowrap;';
      t.appendChild(label);
      var x = document.createElement('span');
      x.textContent = '\u00d7';
      x.style.cssText = 'width:16px;height:16px;line-height:14px;text-align:center;' +
        'border-radius:50%;cursor:pointer;font-size:12px;flex:0 0 auto;' +
        'color:rgba(255,255,255,0.6);';
      x.onclick = function (e) {
        e.stopPropagation();
        try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
      };
      t.onclick = function () {
        if (idx !== cur && window.pywebview && pywebview.api) {
          try { pywebview.api.switch_tab(idx); } catch (err) {}
        }
      };
      t.onauxclick = function (e) {
        if (e.button !== 1) return;
        e.preventDefault();
        try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
      };
      t.appendChild(x);
      return t;
    }
    for (var i = 0; i < tabs.length; i++) { V.appendChild(mkTab(i)); }
    var nb = document.createElement('div');
    nb.textContent = '+ 新建标签';
    nb.style.cssText = 'height:28px;line-height:28px;text-align:center;' +
      'border-radius:6px;cursor:pointer;font-size:12px;margin-top:4px;' +
      'color:rgba(255,255,255,0.75);background:rgba(255,255,255,0.06);';
    nb.onclick = function () {
      try { if (window.pywebview && pywebview.api) pywebview.api.new_tab(); } catch (err) {}
    };
    V.appendChild(nb);
    document.documentElement.appendChild(V);
  } catch (e) { /* 垂直标签栏失败静默：回退顶部标签布局 */ }
})();
"""


def _inject_vtabs_data(tabs_snapshot: dict) -> str:
    """把标签快照作为 window.__aegis_vtabs_data 注入（垂直标签栏读取）。"""
    return (
        "window.__aegis_vtabs_data=" + json.dumps(tabs_snapshot) + ";"
    )


def build_toolbar_js(current_url: str, tabs_snapshot: dict,
                     keybindings: dict | None = None,
                     tabs_position: str = "top",
                     font_family: str = "",
                     search_suggestions: bool = True) -> str:
    """把当前 URL / 标签快照 / 快捷键表注入占位符，返回可 evaluate 的完整脚本。

    keybindings 为 None 时用 DEFAULT_KEYBINDINGS（默认表）；调用方可传入
    用户覆盖后的生效表。tabs_position 支持 "top"（默认顶部标签条）与
    "left"（追加左侧垂直标签栏，对应 config.tabs_position）。
    font_family 非空时覆盖默认字体栈（对应 config.font_family，苹果风格）。
    search_suggestions 对应 config.search_suggestions（影子字段接入：
    关闭时地址栏不显示联想，回车导航不受影响）。
    占位符值一律经 json.dumps 注入 —— 输出永远是合法 JSON 字面量，
    无论 URL / 标题含什么字符都不会造成 JS 注入。
    """
    kb = DEFAULT_KEYBINDINGS if keybindings is None else dict(keybindings)
    js = (
        TOOLBAR_JS
        .replace("__AEGIS_URL__", json.dumps(current_url))
        .replace("__TABS_JSON__", json.dumps(tabs_snapshot))
        .replace("__KEYBINDINGS_JSON__", json.dumps(kb))
        .replace("__FONT_FAMILY__", json.dumps(font_family or ""))
        .replace("__SEARCH_SUGGEST__", "true" if search_suggestions else "false")
    )
    if tabs_position == "left":
        # 先注入垂直标签栏所需的数据，再追加垂直标签栏脚本
        js += _inject_vtabs_data(tabs_snapshot) + VERTICAL_TABS_JS
    return js

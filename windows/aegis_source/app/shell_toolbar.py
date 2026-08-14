# -*- coding: utf-8 -*-
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

# 注入式工具栏：单行紧凑设计（苹果风格）。
# - 高度 40px，毛玻璃半透明深蓝紫（与 aurora 壁纸同色系），白色文字
# - 左侧标签条（紧凑胶囊）+ 新建标签 + 后退/前进/刷新/主页 + 地址栏
# Python 侧把标签数据（__TABS_JSON__）与当前网址（__AEGIS_URL__）
# 直接内嵌进脚本，一次 evaluate 完成渲染 —— 零 HTTP 往返。
TOOLBAR_JS = r"""
(function () {
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
      'font-family:system-ui,-apple-system,"SF Pro Text","Segoe UI",sans-serif'
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
        label.textContent = (tabs[idx] && tabs[idx].title) || '新标签页';
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
  } catch (e) { /* 注入失败绝不影响页面本身 */ }
})();
"""


def build_toolbar_js(current_url: str, tabs_snapshot: dict) -> str:
    """把当前 URL 与标签快照注入占位符，返回可 evaluate 的完整脚本。

    占位符值一律经 json.dumps 注入 —— 输出永远是合法 JSON 字面量，
    无论 URL / 标题含什么字符都不会造成 JS 注入或语法错误。
    """
    return (
        TOOLBAR_JS
        .replace("__AEGIS_URL__", json.dumps(current_url))
        .replace("__TABS_JSON__", json.dumps(tabs_snapshot))
    )

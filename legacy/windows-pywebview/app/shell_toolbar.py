"""shell_toolbar.py —— 注入式工具栏脚本（单文件单职责）。

Apple 设计语言版（参照 docs/DESIGN.md apple 设计规范）：
- SF Pro 字体系统
- 白色/珠光灰背景（#fafafc / #f5f5f7）
- Action Blue (#0066cc) 交互色
- 胶囊圆角按钮（pill radius）
- 极简、无装饰、内容优先

职责：提供 Aegis 浏览器每一页顶部的注入式工具栏（标签条 / 导航按钮 /
地址栏 / 右键菜单 / 复制粘贴）的完整 JS 脚本。
"""

import json

from .tabstrip_js import TABSTRIP_JS

DEFAULT_KEYBINDINGS: dict[str, str] = {
    "new_tab": "t",
    "close_tab": "w",
    "focus_url": "l",
    "copy": "c",
    "paste": "v",
    "select_all": "a",
    "find": "f",
}

TOOLBAR_JS = r"""
(function () {
  function bootUI() {
  try {
    if (document.getElementById('aegis-chrome')) return;
    var TABS_DATA = __TABS_JSON__;
    // 标签条数据全局化：tabstrip_js.TABSTRIP_JS 由此读取并渲染
    // （B0-W-01：bridge_hooks 仅对受信本地页注入真实快照——远程页为空）
    window.__AEGIS_TABS__ = TABS_DATA;

    // === Apple Design System Tokens ===
    var COLORS = {
      primary: '#0066cc',
      primaryHover: '#0071e3',
      ink: '#1d1d1f',
      bodyMuted: '#86868b',
      canvas: '#ffffff',
      canvasParchment: '#f5f5f7',
      surfacePearl: '#fafafc',
      hairline: '#e0e0e0',
      divider: '#f0f0f0',
      onPrimary: '#ffffff',
      chipBg: '#d2d2d7'
    };
    var FONT = 'SF Pro Text, system-ui, -apple-system, '
      + '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif';
    var RADIUS = { xs: 5, sm: 8, md: 11, lg: 18, pill: 9999 };

    // === 主工具栏容器 ===
    var bar = document.createElement('div');
    bar.id = 'aegis-chrome';
    bar.style.cssText = [
      'position:fixed', 'top:0', 'left:0', 'right:0', 'height:48px',
      'z-index:2147483647', 'display:flex', 'align-items:center',
      'gap:8px', 'padding:0 12px',
      'background:' + COLORS.canvas,
      'border-bottom:1px solid ' + COLORS.hairline,
      'box-shadow:0 0.5px 0 ' + COLORS.hairline,
      'box-sizing:border-box',
      'font-family:' + FONT
    ].join(';');

    // === 标签条（容器——渲染/拖拽/右键菜单在 tabstrip_js.TABSTRIP_JS，
    // 单文件单职责；数据经 window.__AEGIS_TABS__ 传递） ===
    var tabsWrap = document.createElement('div');
    tabsWrap.id = 'aegis-tabs';
    tabsWrap.style.cssText = 'display:flex;align-items:center;gap:4px;height:32px;' +
      'overflow:hidden;flex:0 1 auto;min-width:0;max-width:50%;';
    bar.appendChild(tabsWrap);

    // === 分隔线 ===
    var sep = document.createElement('div');
    sep.style.cssText = 'width:1px;height:20px;background:' + COLORS.hairline + ';flex:0 0 auto;';
    bar.appendChild(sep);

    // === 导航按钮（Apple 风格胶囊图标） ===
    function navBtn(glyph, title, act) {
      var b = document.createElement('button');
      b.textContent = glyph; b.title = title;
      b.style.cssText = 'width:30px;height:30px;border:0;background:transparent;' +
        'border-radius:' + RADIUS.sm + 'px;font-size:15px;cursor:pointer;' +
        'color:' + COLORS.ink + ';flex:0 0 auto;line-height:1;' +
        'transition:background 0.15s ease;display:flex;align-items:center;justify-content:center;';
      b.onmouseenter = function(){ b.style.background = COLORS.canvasParchment; };
      b.onmouseleave = function(){ b.style.background = 'transparent'; };
      b.onclick = function(){
        try { if (window.pywebview && pywebview.api) pywebview.api[act](); } catch (e) {}
      };
      bar.appendChild(b);
      return b;
    }
    navBtn('\u2190', '后退', 'go_back');
    navBtn('\u2192', '前进', 'go_forward');
    navBtn('\u21bb', '刷新', 'reload_page');
    navBtn('\u2302', '主页', 'go_home');

    // === 地址栏（Apple 风格胶囊搜索框） ===
    var inpWrap = document.createElement('div');
    inpWrap.style.cssText = 'flex:1;min-width:0;height:32px;display:flex;align-items:center;' +
      'background:' + COLORS.canvasParchment + ';border-radius:' + RADIUS.pill + 'px;' +
      'padding:0 14px;border:1px solid ' + COLORS.hairline + ';' +
      'transition:border-color 0.15s ease;';
    inpWrap.onfocus = function(){ inpWrap.style.borderColor = COLORS.primary; };

    var inp = document.createElement('input');
    inp.id = 'aegis-url';
    inp.spellcheck = false;
    inp.value = '__AEGIS_URL__';
    inp.style.cssText = 'flex:1;min-width:0;border:0;outline:none;background:transparent;' +
      'font-size:13px;color:' + COLORS.ink + ';font-family:' + FONT + ';';
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && window.pywebview && pywebview.api) {
        try { pywebview.api.navigate(inp.value); } catch (err) {}
      }
    });
    inpWrap.appendChild(inp);
    bar.appendChild(inpWrap);

    // === 工具按钮（右侧） ===
    function toolBtn(glyph, title, act) {
      var b = document.createElement('button');
      b.textContent = glyph; b.title = title;
      b.style.cssText = 'width:30px;height:30px;border:0;background:transparent;' +
        'border-radius:' + RADIUS.sm + 'px;font-size:14px;cursor:pointer;' +
        'color:' + COLORS.bodyMuted + ';flex:0 0 auto;line-height:1;' +
        'transition:background 0.15s ease;display:flex;align-items:center;justify-content:center;';
      b.onmouseenter = function(){ b.style.background = COLORS.canvasParchment; };
      b.onmouseleave = function(){ b.style.background = 'transparent'; };
      b.onclick = function(){
        try { if (window.pywebview && pywebview.api) pywebview.api[act](); } catch (e) {}
      };
      bar.appendChild(b);
      return b;
    }
    toolBtn('\u2261', '菜单', 'show_menu');

    // === 右键上下文菜单 ===
    var ctxMenu = document.createElement('div');
    ctxMenu.id = 'aegis-ctx-menu';
    ctxMenu.style.cssText = 'position:fixed;display:none;z-index:2147483647;' +
      'background:' + COLORS.canvas + ';border:1px solid ' + COLORS.hairline + ';' +
      'border-radius:' + RADIUS.md + 'px;padding:4px 0;min-width:180px;' +
      'box-shadow:0 4px 16px rgba(0,0,0,0.12);font-family:' + FONT + ';';
    document.body.appendChild(ctxMenu);

    function showCtxMenu(x, y, items) {
      ctxMenu.textContent = '';
      for (var i = 0; i < items.length; i++) {
        (function(item) {
          if (item.separator) {
            var sep = document.createElement('div');
            sep.style.cssText = 'height:1px;background:' + COLORS.hairline + ';margin:4px 0;';
            ctxMenu.appendChild(sep);
            return;
          }
          var row = document.createElement('div');
          row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;' +
            'padding:6px 16px;cursor:pointer;font-size:13px;color:' + COLORS.ink + ';' +
            'transition:background 0.1s ease;';
          var label = document.createElement('span');
          label.textContent = item.label;
          var shortcut = document.createElement('span');
          shortcut.textContent = item.shortcut || '';
          shortcut.style.cssText = 'color:' + COLORS.bodyMuted + ';font-size:12px;margin-left:24px;';
          row.appendChild(label);
          row.appendChild(shortcut);
          row.onmouseenter = function(){ row.style.background = COLORS.canvasParchment; };
          row.onmouseleave = function(){ row.style.background = 'transparent'; };
          row.onclick = function() { ctxMenu.style.display = 'none'; if (item.action) item.action(); };
          ctxMenu.appendChild(row);
        })(items[i]);
      }
      // 定位（防止超出屏幕）
      var menuW = 200, menuH = items.length * 32;
      if (x + menuW > window.innerWidth) x = window.innerWidth - menuW - 8;
      if (y + menuH > window.innerHeight) y = window.innerHeight - menuH - 8;
      ctxMenu.style.left = x + 'px';
      ctxMenu.style.top = y + 'px';
      ctxMenu.style.display = 'block';
    }

    function hideCtxMenu() { ctxMenu.style.display = 'none'; }

    // 右键事件
    document.addEventListener('contextmenu', function(e) {
      e.preventDefault();
      var sel = window.getSelection ? window.getSelection().toString() : '';
      var link = e.target.closest ? e.target.closest('a[href]') : null;
      var items = [];
      if (link) {
        items.push({label: '在新标签页打开链接', action: function() {
          try { if (window.pywebview && pywebview.api) pywebview.api.navigate(link.href); } catch(err) {}
        }});
        items.push({label: '复制链接地址', shortcut: '', action: function() {
          navigator.clipboard.writeText(link.href).catch(function(){});
        }});
        items.push({separator: true});
      }
      if (sel) {
        items.push({label: '复制', shortcut: 'Ctrl+C', action: function() {
          document.execCommand('copy');
        }});
        items.push({label: '搜索"' + sel.substring(0, 20) + (sel.length > 20 ? '...' : '') + '"', action: function() {
          try { if (window.pywebview && pywebview.api) pywebview.api.navigate(sel); } catch(err) {}
        }});
        items.push({separator: true});
      }
      items.push({label: '粘贴', shortcut: 'Ctrl+V', action: function() {
        navigator.clipboard.readText().then(function(text) {
          var el = document.activeElement;
          if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
            document.execCommand('insertText', false, text);
          }
        }).catch(function(){});
      }});
      items.push({label: '全选', shortcut: 'Ctrl+A', action: function() {
        document.execCommand('selectall');
      }});
      items.push({separator: true});
      items.push({label: '刷新', shortcut: 'Ctrl+R', action: function() {
        try { if (window.pywebview && pywebview.api) pywebview.api.reload_page(); } catch(err) {}
      }});
      items.push({label: '查看页面源代码', action: function() {
        try { if (window.pywebview && pywebview.api) pywebview.api.view_source(); } catch(err) {}
      }});
      showCtxMenu(e.clientX, e.clientY, items);
    });

    // 点击其他地方关闭菜单
    document.addEventListener('click', hideCtxMenu);
    document.addEventListener('keydown', function(e) { if (e.key === 'Escape') hideCtxMenu(); });

    // === 挂载工具栏 ===
    var root = document.documentElement || document;
    root.appendChild(bar);
    if (document.body) document.body.style.marginTop = '48px';

    // === JS 错误上报 ===
    if (window.pywebview && pywebview.api && !window.__aegis_err_hooked) {
      window.__aegis_err_hooked = true;
      window.addEventListener('error', function (e) {
        try {
          pywebview.api.js_error(e.message || 'unknown', e.filename || '', e.lineno, e.colno,
            (e.error && e.error.stack) || '');
        } catch (err) {}
      });
    }

    // === 快捷键 ===
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
            // Ctrl+W 修复：TABS_DATA.current 是注入时刻的冻结快照（多标签
            // 下会关错）——改用后端实时 _current（tab_ops.close_current_tab）
            pywebview.api.close_current_tab();
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

  // 三重保险初始化
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

VERTICAL_TABS_JS = r"""
(function () {
  try {
    if (document.getElementById('aegis-vtabs')) return;
    if (document.getElementById('aegis-chrome')) {
      document.body.style.marginLeft = '200px';
    }
    var COLORS = {
      canvas: '#ffffff',
      canvasParchment: '#f5f5f7',
      ink: '#1d1d1f',
      bodyMuted: '#86868b',
      hairline: '#e0e0e0',
      primary: '#0066cc'
    };
    var FONT = 'SF Pro Text, system-ui, -apple-system, "Segoe UI", "PingFang SC", sans-serif';

    var V = document.createElement('div');
    V.id = 'aegis-vtabs';
    V.style.cssText = 'position:fixed;top:48px;left:0;bottom:0;width:200px;' +
      'overflow-y:auto;background:' + COLORS.canvas + ';' +
      'border-right:1px solid ' + COLORS.hairline + ';' +
      'z-index:2147483646;box-sizing:border-box;padding:8px;font-family:' + FONT + ';';

    var data = window.__aegis_vtabs_data || {};
    var tabs = (data && data.tabs) || [];
    var cur = (data && data.current) || 0;

    function mkTab(idx) {
      var isActive = (idx === cur);
      var t = document.createElement('div');
      t.style.cssText = 'display:flex;align-items:center;gap:8px;height:36px;' +
        'padding:0 10px;border-radius:8px;cursor:pointer;font-size:13px;' +
        'color:' + (isActive ? COLORS.ink : COLORS.bodyMuted) + ';' +
        'background:' + (isActive ? COLORS.canvasParchment : 'transparent') + ';' +
        'font-weight:' + (isActive ? '500' : '400') + ';margin-bottom:2px;' +
        'transition:background 0.15s ease;';

      var label = document.createElement('span');
      var tp = (tabs[idx] && tabs[idx].pinned) ? '\u{1F4CC} ' : '';
      label.textContent = tp + ((tabs[idx] && tabs[idx].title) || '新标签页');
      label.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

      var x = document.createElement('span');
      x.textContent = '\u00d7';
      x.style.cssText = 'width:16px;height:16px;line-height:14px;text-align:center;' +
        'border-radius:50%;cursor:pointer;font-size:11px;flex:0 0 auto;' +
        'color:' + COLORS.bodyMuted + ';';
      x.onclick = function (e) {
        e.stopPropagation();
        try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
      };
      t.onmouseenter = function(){ if (!isActive) t.style.background = COLORS.canvasParchment; };
      t.onmouseleave = function(){ if (!isActive) t.style.background = 'transparent'; };
      t.onclick = function () {
        if (idx !== cur && window.pywebview && pywebview.api) {
          try { pywebview.api.switch_tab(idx); } catch (err) {}
        }
      };
      t.appendChild(label);
      t.appendChild(x);
      return t;
    }

    for (var i = 0; i < tabs.length; i++) { V.appendChild(mkTab(i)); }

    var nb = document.createElement('div');
    nb.textContent = '+ 新建标签';
    nb.style.cssText = 'height:32px;line-height:32px;text-align:center;' +
      'border-radius:8px;cursor:pointer;font-size:13px;margin-top:8px;' +
      'color:' + COLORS.primary + ';background:' + COLORS.canvasParchment + ';';
    nb.onclick = function () {
      try { if (window.pywebview && pywebview.api) pywebview.api.new_tab(); } catch (err) {}
    };
    V.appendChild(nb);
    (document.documentElement || document).appendChild(V);
  } catch (e) {}
})();
"""


def build_toolbar_js(
    current_url: str,
    tabs_snapshot: dict,
    *,
    keybindings: dict | None = None,
    tabs_position: str = "top",
    search_suggestions: bool = True,
) -> str:
    """构建完整的注入式工具栏 JS（替换占位符后可直接 evaluate）。"""
    kb = keybindings if keybindings is not None else DEFAULT_KEYBINDINGS
    tabs_json = json.dumps(tabs_snapshot, ensure_ascii=False)
    kb_json = json.dumps(kb, ensure_ascii=False)
    font_family = 'SF Pro Text, system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'

    js = TOOLBAR_JS
    js = js.replace("__TABS_JSON__", tabs_json)
    js = js.replace("__AEGIS_URL__", json.dumps(current_url)[1:-1])
    js = js.replace("__KEYBINDINGS_JSON__", kb_json)
    js = js.replace("__SEARCH_SUGGEST__", "true" if search_suggestions else "false")
    js = js.replace("__FONT_FAMILY__", json.dumps(font_family))

    # 标签条（拖拽排序/固定菜单/中键关闭）——独立脚本段（单文件单职责）；
    # 数据经 window.__AEGIS_TABS__ 共享，无需额外占位符
    js += "\n" + TABSTRIP_JS

    if tabs_position == "left":
        js += "\n" + VERTICAL_TABS_JS
    return js

"""tabstrip_js.py —— 注入式标签条脚本（单文件单职责）。

CHANGELOG「Unreleased/Planned：Windows 标签增强」落地：
- 拖拽排序（HTML5 之外的 mouse 事件实现——WebView2 下兼容性最稳）；
- 标签右键菜单（固定/取消固定——后端 pin_tab/unpin_tab 首次获得 UI 入口）；
- 中键关闭（onauxclick，自 shell_toolbar 迁移并保留）；
- 本地重渲染（排序/固定后无需等待页面重载——同步更新 __AEGIS_TABS__）。

安全边界（B0-W-01 口径不变）：
- 数据来源 window.__AEGIS_TABS__，由 bridge_hooks 仅对受信本地页注入
  （脱敏：title/pinned/group，无 URL）；远程页面注入空快照——本脚本
  无标签可渲染，拖拽/固定/关闭自然不可达；
- 全部写操作经 pywebview.api（远程页面还会被 _check_trusted_source 拒绝）；
- 本地重排逻辑与后端 move_tab/pin_tab 的 pinned 区钳制语义逐行对齐
  （后端仍为准——两端不一致时以桥返回后的真实快照为准，下次注入校正）。
"""

TABSTRIP_JS = r"""
(function () {
  try {
    // 防重复钩子（TOOLBAR_JS 的 bootUI 可多次触发——三重保险初始化）
    if (window.__aegis_tabstrip_booted) return;
    window.__aegis_tabstrip_booted = true;
    var COLORS = {
      ink: '#1d1d1f', bodyMuted: '#86868b',
      canvasParchment: '#f5f5f7', divider: '#f0f0f0',
      hairline: '#e0e0e0', chipBg: '#d2d2d7',
      primary: '#0066cc', canvas: '#ffffff'
    };
    var FONT = 'SF Pro Text, system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif';
    var R = 8;
    var wrap = null;  // #aegis-tabs 容器（TOOLBAR_JS bootUI 挂载后可用）

    function data() { return window.__AEGIS_TABS__ || {}; }

    function mkTab(idx) {
      var d = data();
      var tabs = d.tabs || [], cur = d.current || 0;
      var isActive = (idx === cur);
      var t = document.createElement('div');
      t.dataset.tidx = idx;
      t.style.cssText = 'display:inline-flex;align-items:center;gap:6px;max-width:140px;height:30px;' +
        'padding:0 8px 0 12px;border-radius:' + R + 'px;cursor:pointer;font-size:13px;' +
        'color:' + (isActive ? COLORS.ink : COLORS.bodyMuted) + ';' +
        'background:' + (isActive ? COLORS.canvasParchment : 'transparent') + ';' +
        'font-weight:' + (isActive ? '500' : '400') + ';' +
        'transition:background 0.15s ease;user-select:none;';

      var label = document.createElement('span');
      var isPin = !!(tabs[idx] && tabs[idx].pinned);
      label.textContent = (isPin ? '\u{1F4CC} ' : '') + ((tabs[idx] && tabs[idx].title) || '新标签页');
      label.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;';

      var x = document.createElement('span');
      x.textContent = '\u00d7';
      x.style.cssText = 'width:16px;height:16px;line-height:14px;text-align:center;border-radius:50%;' +
        'cursor:pointer;color:' + COLORS.bodyMuted + ';font-size:11px;flex:0 0 auto;' +
        'transition:background 0.15s ease;';
      x.onmouseenter = function(){ x.style.background = COLORS.chipBg; };
      x.onmouseleave = function(){ x.style.background = 'transparent'; };
      x.onclick = function (e) {
        e.stopPropagation();
        try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
      };

      t.onmouseenter = function(){ if (!isActive) t.style.background = COLORS.divider; };
      t.onmouseleave = function(){ if (!isActive) t.style.background = 'transparent'; };
      t.onclick = function () {
        if (idx !== cur && window.pywebview && pywebview.api) {
          try { pywebview.api.switch_tab(idx); } catch (err) {}
        }
      };
      // 中键关闭（鼠标 auxiliary button 1）
      t.onauxclick = function (e) {
        if (e.button !== 1) return;
        e.preventDefault();
        try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
      };
      // 右键菜单：固定/取消固定 + 关闭
      t.oncontextmenu = function (e) { e.preventDefault(); e.stopPropagation(); showTabMenu(e, idx); };
      // 拖拽排序（左键按住移动 ≥4px 触发）
      t.onmousedown = function (e) { if (e.button === 0) startDrag(e, idx, t); };

      t.appendChild(label);
      t.appendChild(x);
      return t;
    }

    function mkNewBtn() {
      var nb = document.createElement('div');
      nb.textContent = '+';
      nb.title = '新标签页 (Ctrl+T)';
      nb.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;' +
        'width:28px;height:28px;border-radius:' + R + 'px;cursor:pointer;' +
        'color:' + COLORS.bodyMuted + ';font-size:18px;font-weight:300;flex:0 0 auto;' +
        'transition:background 0.15s ease;';
      nb.onmouseenter = function(){ nb.style.background = COLORS.canvasParchment; };
      nb.onmouseleave = function(){ nb.style.background = 'transparent'; };
      nb.onclick = function () {
        try { if (window.pywebview && pywebview.api) pywebview.api.new_tab(); } catch (err) {}
      };
      return nb;
    }

    function render() {
      var d = data();
      var tabs = d.tabs || [];
      wrap.textContent = '';
      for (var i = 0; i < tabs.length; i++) wrap.appendChild(mkTab(i));
      wrap.appendChild(mkNewBtn());
    }

    // === 本地状态同步（与后端 move/pin 语义对齐；后端为准，重载校正） ===
    function localMove(from, to) {
      var d = data();
      var tabs = d.tabs || [];
      if (from === to || from < 0 || from >= tabs.length) return;
      to = clampTarget(from, to, tabs);
      if (from === to) { render(); return; }
      var moved = tabs.splice(from, 1)[0];
      tabs.splice(to, 0, moved);
      if (d.current === from) d.current = to;
      else if (from < d.current && d.current <= to) d.current--;
      else if (to <= d.current && d.current < from) d.current++;
      render();
    }

    function clampTarget(from, to, tabs) {
      // pinned 只能在 pinned 区内重排；普通标签不越过 pinned 区（后端同规则）
      var np = 0;
      for (var i = 0; i < tabs.length; i++) if (tabs[i] && tabs[i].pinned) np++;
      if (tabs[from] && tabs[from].pinned) return Math.max(0, Math.min(to, np - 1));
      return Math.min(Math.max(to, np), tabs.length - 1);
    }

    function localPin(idx, pin) {
      var d = data();
      var tabs = d.tabs || [];
      if (!(idx >= 0 && idx < tabs.length)) return;
      tabs[idx].pinned = pin;
      var pinArr = [], norm = [];
      for (var i = 0; i < tabs.length; i++) (tabs[i].pinned ? pinArr : norm).push(tabs[i]);
      var curTab = tabs[idx];
      d.tabs = pinArr.concat(norm);
      d.current = d.tabs.indexOf(curTab);
      render();
    }

    // === 标签右键菜单 ===
    function removeTabMenu() {
      var m = document.getElementById('aegis-tab-menu');
      if (m) m.remove();
      document.removeEventListener('click', removeTabMenu, true);
    }
    function showTabMenu(e, idx) {
      removeTabMenu();
      var pinned = !!(data().tabs[idx] && data().tabs[idx].pinned);
      var m = document.createElement('div');
      m.id = 'aegis-tab-menu';
      m.style.cssText = 'position:fixed;z-index:2147483647;background:' + COLORS.canvas + ';' +
        'border:1px solid ' + COLORS.hairline + ';border-radius:11px;padding:4px 0;' +
        'min-width:140px;box-shadow:0 4px 16px rgba(0,0,0,0.12);font-family:' + FONT + ';';
      function row(label, fn) {
        var r = document.createElement('div');
        r.textContent = label;
        r.style.cssText = 'padding:6px 16px;cursor:pointer;font-size:13px;color:' + COLORS.ink + ';';
        r.onmouseenter = function(){ r.style.background = COLORS.canvasParchment; };
        r.onmouseleave = function(){ r.style.background = 'transparent'; };
        r.onclick = function () {
          removeTabMenu();
          try {
            if (window.pywebview && pywebview.api) {
              if (fn === 'pin') { pywebview.api.pin_tab(idx); localPin(idx, true); }
              else if (fn === 'unpin') { pywebview.api.unpin_tab(idx); localPin(idx, false); }
              else if (fn === 'close') { pywebview.api.close_tab(idx); }
            }
          } catch (err) {}
        };
        m.appendChild(r);
      }
      row(pinned ? '取消固定' : '固定标签', pinned ? 'unpin' : 'pin');
      row('关闭标签', 'close');
      document.body.appendChild(m);
      var mw = 150, mh = 72;
      var px = Math.min(e.clientX, window.innerWidth - mw - 8);
      var py = Math.min(e.clientY, window.innerHeight - mh - 8);
      m.style.left = px + 'px';
      m.style.top = py + 'px';
      setTimeout(function(){ document.addEventListener('click', removeTabMenu, true); }, 0);
    }

    // === 拖拽排序 ===
    var drag = null;
    function startDrag(e, idx, el) {
      drag = { from: idx, el: el, started: false, x0: e.clientX, y0: e.clientY };
    }
    document.addEventListener('mousemove', function (e) {
      if (!drag) return;
      if (!drag.started) {
        if (Math.abs(e.clientX - drag.x0) < 4 && Math.abs(e.clientY - drag.y0) < 4) return;
        drag.started = true;
        drag.el.style.opacity = '0.45';
      }
      var target = pickDropIndex(e.clientX);
      var els = tabEls();
      for (var i = 0; i < els.length; i++) {
        els[i].style.borderTop = (target === parseInt(els[i].dataset.tidx, 10))
          ? ('2px solid ' + COLORS.primary) : '';
      }
    });
    document.addEventListener('mouseup', function (e) {
      if (!drag) return;
      var d = drag;
      drag = null;
      d.el.style.opacity = '';
      var els = tabEls();
      for (var i = 0; i < els.length; i++) els[i].style.borderTop = '';
      if (!d.started) return;
      var to = pickDropIndex(e.clientX);
      if (to === null || to === d.from) return;
      try { if (window.pywebview && pywebview.api) pywebview.api.move_tab(d.from, to); } catch (err) {}
      localMove(d.from, to);
    });
    function tabEls() {
      var out = [];
      for (var i = 0; i < wrap.children.length; i++) {
        var c = wrap.children[i];
        if (c.dataset && c.dataset.tidx !== undefined) out.push(c);
      }
      return out;
    }
    function pickDropIndex(px) {
      var els = tabEls();
      if (!els.length) return null;
      for (var i = 0; i < els.length; i++) {
        var r = els[i].getBoundingClientRect();
        if (px < r.left + r.width / 2) return parseInt(els[i].dataset.tidx, 10);
      }
      return parseInt(els[els.length - 1].dataset.tidx, 10);
    }

    // === 挂载等待：TOOLBAR_JS 的 bootUI 在 pywebviewready 后才创建
    // #aegis-tabs 容器——轮询等挂载（50ms × 100 次 = 5s 上限）后渲染 ===
    var tries = 0;
    (function waitMount() {
      var w = document.getElementById('aegis-tabs');
      if (w) { wrap = w; render(); return; }
      if (++tries > 100) return;  // 容器始终未挂载（注入失败）→ 静默放弃
      setTimeout(waitMount, 50);
    })();
  } catch (e) { /* 标签条失败绝不影响页面本身 */ }
})();
"""

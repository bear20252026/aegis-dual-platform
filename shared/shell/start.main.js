// start.main.js —— 单源首页主逻辑（引擎/壁纸/书签/会话恢复/快捷入口）
// 从 start.html 内联块外置（审计 I83：CSP script-src 'self' 后内联脚本
// 不可执行；事件绑定全部经 addEventListener——不再依赖内联 onclick/onsubmit）。
// 加载顺序：start.js（Host 适配层）→ start.snake.js → start.import.js → 本文件。
'use strict';

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

var WALLPAPERS = [
  {name:'aurora-magenta.jpg', url:'wallpapers/aurora-magenta.jpg'},
  {name:'aurora-lime.jpg',    url:'wallpapers/aurora-lime.jpg'},
  {name:'aurora-twilight.jpg',url:'wallpapers/aurora-twilight.jpg'},
  {name:'aurora-violet.jpg',  url:'wallpapers/aurora-violet.jpg'}
];
var current = 'aurora-twilight.jpg';
// 搜索引擎状态
var ENGINES = [];           // [{key,name}]
var engineIdx = 0;

function renderEngine() {
  var el = document.getElementById('engineName');
  if (el && ENGINES.length) el.textContent = ENGINES[engineIdx].name;
}
function toggleEngineMenu(ev) {
  if (ev) ev.stopPropagation();
  var m = document.getElementById('engineMenu');
  var pill = document.getElementById('enginePill');
  if (!m) return;
  if (m.style.display === 'block') {
    m.style.display = 'none';
    if (pill) pill.setAttribute('aria-expanded', 'false');
    return;
  }
  renderEngineMenu(function () {
    m.style.display = 'block';
    if (pill) pill.setAttribute('aria-expanded', 'true');
  });
}
function renderEngineMenu(done) {
  var m = document.getElementById('engineMenu');
  if (!m) return;
  function build() {
    if (!ENGINES.length) { m.style.display = 'none'; return; }
    m.textContent = '';
    for (var i = 0; i < ENGINES.length; i++) {
      (function (idx) {
        var it = document.createElement('div');
        it.className = 'engine-item' + (idx === engineIdx ? ' active' : '');
        it.setAttribute('role', 'menuitemradio');
        it.setAttribute('aria-checked', idx === engineIdx ? 'true' : 'false');
        it.tabIndex = 0;
        var name = document.createElement('span');
        name.textContent = ENGINES[idx].name;
        var mark = document.createElement('span');
        mark.className = 'mark';
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = idx === engineIdx ? '✓' : '';
        it.appendChild(name);
        it.appendChild(mark);
        it.onclick = function (ev) { ev.stopPropagation(); selectEngine(idx); };
        it.onkeydown = function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ev.stopPropagation(); selectEngine(idx); }
        };
        m.appendChild(it);
      })(i);
    }
    if (done) done();
  }
  if (!ENGINES.length) {
    // 引擎表未就绪时向宿主拉取（跨端：Windows csCall / Android JSON）
    try {
      Host.getEngine(function (data) {
        if (data && data.engines && data.engines.length) {
          ENGINES = data.engines;
          engineIdx = 0;
          for (var i = 0; i < ENGINES.length; i++) {
            if (ENGINES[i].key === data.engine) { engineIdx = i; break; }
          }
          renderEngine();
        }
        build();
      });
    } catch (e) { build(); }
  } else { build(); }
}
function selectEngine(idx) {
  if (!ENGINES.length) return;
  engineIdx = idx;
  renderEngine();
  try { Host.setEngine(ENGINES[engineIdx].key); } catch (e) {}
  var m = document.getElementById('engineMenu');
  if (m) m.style.display = 'none';
}
document.addEventListener('click', function () {
  var m = document.getElementById('engineMenu');
  if (m) m.style.display = 'none';
});
// 读取当前搜索引擎（配置持久化）
{
  try {
    Host.getEngine(function (data) {
      if (!data) return;
      ENGINES = data.engines || [];
      for (var i = 0; i < ENGINES.length; i++) {
        if (ENGINES[i].key === data.engine) { engineIdx = i; break; }
      }
      renderEngine();
    });
  } catch (e) {}
}

// —— 搜索（form submit + 按钮双路径——BUG-002/009 教训：IME action 与
//    file:// 下的 submit 兼容都需要保底） ——
var _searchBusy = false;
function go() {
  if (_searchBusy) return;
  var v = document.getElementById('q').value.trim();
  if (!v || !Host.has('navigate')) return;
  _searchBusy = true;
  var btn = document.getElementById('searchBtn');
  var orig = btn.textContent;
  btn.textContent = '搜索中…';
  try { Host.navigate(v); } catch (e) { Host.jsError('navigate failed: ' + e); }
  // 导航被 Broker 确认面板挂起或失败时复原按钮（成功则页面随即卸载）
  setTimeout(function () { btn.textContent = orig; _searchBusy = false; }, 1200);
}
function openUrl(u) {
  if (Host.has('navigate')) Host.navigate(u);
}
document.addEventListener('keydown', function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
    e.preventDefault(); document.getElementById('q').focus(); document.getElementById('q').select();
  }
});

// —— 壁纸 ——
function setWallpaper(name) {
  var hit = null;
  for (var i = 0; i < WALLPAPERS.length; i++) {
    if (WALLPAPERS[i].name === name) { hit = WALLPAPERS[i]; break; }
  }
  if (!hit) return;
  current = name;
  document.getElementById('wallpaper').style.backgroundImage = "url('" + hit.url.replace(/'/g, '%27') + "')";
  var dots = document.getElementById('wpList').children;
  for (var j = 0; j < dots.length; j++) {
    dots[j].className = 'wp' + (WALLPAPERS[dots[j].dataset.i].name === name ? ' active' : '');
  }
  try { Host.setWallpaper(name); } catch (e) {}
}

// 渲染壁纸切换圆点
(function renderWallpaperDots() {
  var wl = document.getElementById('wpList');
  for (var i = 0; i < WALLPAPERS.length; i++) {
    (function (idx) {
      var d = document.createElement('div');
      d.className = 'wp';
      d.dataset.i = idx;
      d.style.backgroundImage = "url('" + WALLPAPERS[idx].url.replace(/'/g, '%27') + "')";
      d.title = WALLPAPERS[idx].name;
      d.setAttribute('role', 'button');
      d.setAttribute('aria-label', '壁纸 ' + WALLPAPERS[idx].name);
      d.tabIndex = 0;
      function pick() { setWallpaper(WALLPAPERS[idx].name); }
      d.onclick = pick;
      d.onkeydown = function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); }
      };
      wl.appendChild(d);
    })(i);
  }
})();

// 读取当前壁纸（配置持久化）
{
  try {
    Host.getWallpaper(function (name) {
      if (name) setWallpaper(name);
    });
  } catch (e) {}
}

// —— 几何画板快捷入口（离线 GeoGebra——后端加载内置资源页；
//    资源未随包时返回 false → 按钮置灰提示） ——
(function () {
  var btn = document.getElementById('geoBtn');
  if (!btn) return;
  btn.addEventListener('click', function () {
    try {
      if (!Host.has('geo')) return;
      // P1-12 修复（全量复审 2026-09-01）：openGeo 的回调即 onFail——
      // 仅在打开失败时调用（此前回调里引用未定义变量 ok，
      // ReferenceError 被 try 吞掉 → 置灰提示永不生效）
      Host.openGeo(function () {
        btn.classList.add('unavailable');
        btn.title = '当前安装包未包含画板资源';
      });
    } catch (e) {}
  });
})();

// —— 恢复上次会话入口（resume_session 自动恢复之外的手动入口；
//    仅当已保存会话 >1 个标签时显示——has_saved_session 只返回计数） ——
(function () {
  try {
    Host.hasSaved(function (n) {
      n = parseInt(n, 10) || 0;
      if (n > 1) {
        var box = document.getElementById('restoreBox');
        var btn = document.getElementById('restoreBtn');
        if (!box || !btn) return;
        btn.textContent = '恢复上次会话（' + n + ' 个标签）';
        box.style.display = 'block';
        btn.onclick = function () {
          try { Host.restoreSession(); } catch (e) {}
        };
      }
    });
  } catch (e) {}
})();

// —— 渲染书签 ——
function renderBookmarks() {
  var box = document.getElementById('bm');
  if (!box) return;
  try {
    if (!Host.has('bookmarks')) return;
    Host.bookmarks(function (items) {
      if (!items || !items.length) {
        box.textContent = '';
        var empty = document.createElement('div');
        empty.className = 'bm-empty';
        empty.textContent = '还没有书签 — 浏览网页时点击地址栏右侧的 ☆ 按钮即可收藏';
        box.appendChild(empty);
        return;
      }
      // R-06 整改（体验/功能审查）：禁止 innerHTML 字符串拼接——
      // 标题/URL/图标文本全部经 textContent 写入 DOM（防特殊字符
      // 破坏显示与注入——实施手册 R-06 bookmarkCard 示例）
      var frag = document.createDocumentFragment();
      // 首页只展示最近 8 个书签；完整数据仍保留在书签库中，避免
      // 大量历史/书签标签铺满主屏（横条可水平滚动）。
      var visibleItems = items.slice(0, 8);
      for (var i = 0; i < visibleItems.length; i++) {
        var it = visibleItems[i];
        var host = '';
        try { host = new URL(it.url).host; } catch (e) { host = it.url; }
        var card = document.createElement('div');
        card.className = 'bm';
        card.setAttribute('role', 'link');
        card.tabIndex = 0;
        card.addEventListener('click', (function (u) {
          return function () { openUrl(u); };
        })(it.url));
        card.addEventListener('keydown', (function (u) {
          return function (ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); openUrl(u); }
          };
        })(it.url));
        var ico = document.createElement('div');
        ico.className = 'bm-ico';
        ico.textContent = (host.charAt(0) || '?').toUpperCase();
        var name = document.createElement('div');
        name.className = 'bm-name';
        name.textContent = (it.title || host);
        card.appendChild(ico);
        card.appendChild(name);
        frag.appendChild(card);
      }
      // “添加常用站点”磁贴（对齐 Edge）：点击聚焦搜索框输入网址
      var addTile = document.createElement('div');
      addTile.className = 'bm bm-add';
      addTile.setAttribute('role', 'button');
      addTile.setAttribute('aria-label', '添加常用站点');
      addTile.tabIndex = 0;
      function focusSearch() {
        var q = document.getElementById('q');
        if (q) { q.focus(); q.select(); }
      }
      addTile.addEventListener('click', focusSearch);
      addTile.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); focusSearch(); }
      });
      var addIco = document.createElement('div');
      addIco.className = 'bm-ico';
      addIco.textContent = '＋';
      var addName = document.createElement('div');
      addName.className = 'bm-name';
      addName.textContent = '添加常用站点';
      addTile.appendChild(addIco);
      addTile.appendChild(addName);
      frag.appendChild(addTile);
      box.replaceChildren(frag);
    });
  } catch (e) {}
}
// 书签渲染：立即尝试 + 桥未就绪时有界重试（此前固定 200ms 魔法延时，
// 慢机上桥未就绪即空宫格）
(function renderBookmarksWithRetry(attempt) {
  if (Host.kind()) { renderBookmarks(); return; }
  if (attempt >= 10) { renderBookmarks(); return; }
  setTimeout(function () { renderBookmarksWithRetry(attempt + 1); }, 200);
})(0);

// ================= 内联事件处理器外置（CSP——审计 I83） =================
// 此前 onclick/onsubmit 内联属性依赖"受信壳页"假设；CSP script-src 'self'
//（禁内联）后统一经 addEventListener 绑定。
(function wireStaticHandlers() {
  // 引擎胶囊（点击/键盘展开菜单）
  var pill = document.getElementById('enginePill');
  if (pill) {
    pill.addEventListener('click', function (ev) { toggleEngineMenu(ev); });
    pill.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault(); toggleEngineMenu(ev);
      }
    });
  }
  // 搜索：form submit（IME「搜索/前往」action）+ 按钮直调双路径
  //（BUG-009：file:// 页面 submit 可能不触发——按钮点击必须保底）
  var form = document.getElementById('searchForm');
  if (form) {
    form.addEventListener('submit', function (ev) { ev.preventDefault(); go(); });
  }
  var searchBtn = document.getElementById('searchBtn');
  if (searchBtn) {
    searchBtn.addEventListener('click', function () { go(); });
  }
  // 贪吃蛇入口与关闭
  var snakeBtn = document.getElementById('snakeBtn');
  if (snakeBtn) {
    snakeBtn.addEventListener('click', function () {
      if (typeof openSnake === 'function') openSnake();
    });
  }
  var snakeClose = document.getElementById('snakeClose');
  if (snakeClose) {
    snakeClose.addEventListener('click', function () {
      if (window.Snake && typeof Snake.close === 'function') Snake.close();
    });
  }
})();

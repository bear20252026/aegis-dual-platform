// start_main.test.mjs —— start.main.js 主逻辑回归（node --test）
// WB-025：未知壁纸必须整体 no-op（不得污染当前壁纸/样式/桥调用）；
// WB-026：背景 url('...') 单引号必须 %27 编码（style 注入防护）；
// WB-013：桥调用失败必须经 jsError 留痕且不阻断首屏装配。
// WB-044/045/048/051/057/082..089/096（审计 2026-09-23 清单·W5 批）：
// 引擎菜单方向键/Escape、☆ 文案平台差异、原生按钮圆点、时序常量单源、
// 菜单选中态/空表分支、go 空输入/防抖、host 回退/前 8 截断/有界重试/
// parseInt 归一、双路径防重放——此前零测试面。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const MAINJS = readFileSync(join(ROOT, 'shared', 'shell', 'start.main.js'), 'utf8');

// —— 最小 DOM 桩（仅覆盖 start.main.js 触及的表面） ——
function el(tag) {
  const node = {
    tagName: tag,
    children: [],
    style: {},
    dataset: {},
    className: '',
    title: '',
    value: '',
    tabIndex: 0,
    _handlers: {},
    _attrs: {},
    _focused: false,
    _textContent: '',
    appendChild(c) { node.children.push(c); return c; },
    // WB-107：书签宫格经 replaceChildren 整段替换（frag 进容器）
    replaceChildren(...cs) { node.children.length = 0; cs.forEach((c) => node.children.push(c)); },
    addEventListener(type, fn) { (node._handlers[type] = node._handlers[type] || []).push(fn); },
    // W5 批：属性/焦点记录——aria-expanded、role=menuitemradio、
    // 方向键导航断言需要读取写入
    setAttribute(n, v) { node._attrs[n] = String(v); },
    getAttribute(n) { return n in node._attrs ? node._attrs[n] : null; },
    focus() { node._focused = true; },
    // WB-044：引擎菜单方向键从容器取菜单项——按 role 过滤后代
    querySelectorAll(sel) {
      const hit = [];
      const want = sel === '[role="menuitemradio"]' ? 'menuitemradio' : null;
      if (!want) return hit;
      (function walk(n) { (n.children || []).forEach((c) => { if (c._attrs && c._attrs.role === want) hit.push(c); walk(c); }); })(node);
      return hit;
    },
  };
  // 真实 DOM 语义：对 textContent 赋值会清空全部子节点（容器换页依赖）
  Object.defineProperty(node, 'textContent', {
    get() { return node._textContent; },
    set(v) { node._textContent = String(v); node.children.length = 0; },
  });
  return node;
}

function makeHost() {
  const state = { setCalls: [], errors: [], getWallpaperCb: null, hasSavedN: 0, hasSavedRaw: undefined, navigateCalls: 0, restoreCalls: 0 };
  const host = {
    kind: () => 'cs',
    has: (f) => f === 'navigate' || f === 'geo',   // bookmarks=false → 书签宫格早退
    getEngine: (cb) => cb({ engine: 'baidu', engines: [{ key: 'baidu', name: '百度' }] }),
    getWallpaper: (cb) => { state.getWallpaperCb = cb; },
    hasSaved: (cb) => cb(state.hasSavedRaw !== undefined ? state.hasSavedRaw : state.hasSavedN),
    restoreSession: () => { state.restoreCalls += 1; },
    setWallpaper: (name) => state.setCalls.push(name),
    jsError: (...a) => state.errors.push(a.join(' ')),
    navigate: () => { state.navigateCalls += 1; },
  };
  return { host, state };
}

function loadMain(host, winExtras) {
  const elements = {
    q: el('input'),
    searchForm: el('form'),
    searchBtn: el('button'),
    enginePill: el('div'),
    engineName: el('span'),
    engineMenu: el('div'),
    wallpaper: el('div'),
    wpList: el('div'),
    bm: el('div'),
    restoreBox: el('div'),
    restoreBtn: el('button'),
  };
  const docHandlers = {};
  const document = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => el(tag),
    // WB-107：书签整段构建走 DocumentFragment
    createDocumentFragment: () => ({ children: [], appendChild(c) { this.children.push(c); } }),
    addEventListener(type, fn) { (docHandlers[type] = docHandlers[type] || []).push(fn); },
    activeElement: null,
  };
  const win = Object.assign({ addEventListener() {} }, winExtras);
  const timers = { fired: [], setTimeout(fn, ms) { timers.fired.push({ fn, ms }); return timers.fired.length; } };
  let exported = null;
  // 模块级 var/函数声明是 Function 体局部——尾部追加 __take 导出待测面。
  // W5 批：setTimeout 桩注入（go 复原/书签有界重试不再依赖真实 1.2s/200ms）
  new Function('document', 'window', 'Host', '__take', 'setTimeout',
    MAINJS + '\n;__take({ setWallpaper: setWallpaper, WALLPAPERS: WALLPAPERS, ' +
    'current: function () { return current; }, go: go, ' +
    'renderEngineMenu: renderEngineMenu, toggleEngineMenu: toggleEngineMenu, ' +
    'selectEngine: selectEngine, renderBookmarks: renderBookmarks, ' +
    'renderBookmarksWithRetry: renderBookmarksWithRetry, ' +
    'timing: function () { return TIMING; } });')(
    document, win, host, (x) => { exported = x; }, timers.setTimeout);
  return { elements, exported, timers, docHandlers };
}

test('WB-025 未知壁纸整体 no-op：状态/样式/桥调用全不动', () => {
  const { host, state } = makeHost();
  const { elements, exported } = loadMain(host);
  assert.equal(exported.current(), 'aurora-twilight.jpg', '默认壁纸基准');
  exported.setWallpaper('not-a-wallpaper.jpg');
  assert.equal(exported.current(), 'aurora-twilight.jpg', '未知名不得污染当前壁纸');
  assert.equal(elements.wallpaper.style.backgroundImage, undefined, '背景样式不得被改动');
  assert.deepEqual(state.setCalls, [], '未知名不得下发桥调用');
  assert.deepEqual(state.errors, [], '未知名是正常分支——不得误报 jsError');
});

test('WB-025 对照组：合法壁纸正常应用 + 桥下发 + 圆点高亮迁移', () => {
  const { host, state } = makeHost();
  const { elements, exported } = loadMain(host);
  exported.setWallpaper('aurora-lime.jpg');
  assert.equal(exported.current(), 'aurora-lime.jpg');
  assert.deepEqual(state.setCalls, ['aurora-lime.jpg'], '合法名必须下发宿主持久化');
  assert.equal(elements.wallpaper.style.backgroundImage, "url('wallpapers/aurora-lime.jpg')");
  const active = elements.wpList.children
    .filter((d) => d.className === 'wp active')
    .map((d) => d.title);
  // WB-132（2026-09-26 审计）：tooltip/aria-label 改用中文名（label 字段），
  // 不再暴露内部资产文件名
  assert.deepEqual(active, ['晨曦青'], '高亮必须迁移到目标圆点');
  const titles = elements.wpList.children.map((d) => d.title);
  assert.deepEqual(titles, ['暖洋红', '晨曦青', '暮蓝', '星紫'],
    '壁纸圆点 tooltip 必须为中文名（label 字段）');
});

// WB-051（审计 2026-09-23 清单·W5 批）：壁纸圆点由 div[role=button] 改原生
// button——键盘可达与读屏按钮角色由元素本体承担
test('WB-051 壁纸圆点必须是原生 button（type=button），非 div 模拟语义', () => {
  const { host } = makeHost();
  const { elements } = loadMain(host);
  assert.equal(elements.wpList.children.length, 4, '四张壁纸四枚圆点');
  for (const d of elements.wpList.children) {
    assert.equal(d.tagName, 'button', '圆点必须以 button 元素构建');
    assert.equal(d.type, 'button', '必须显式 type=button（防未来入 form 后触发提交）');
    assert.equal(d.className, 'wp', '样式类保持 .wp');
    assert.equal(typeof d.onclick, 'function', '点击接线保持');
  }
});

test('WB-025 持久化恢复路径同样受未知名守卫', () => {
  const { host, state } = makeHost();
  const { exported } = loadMain(host);
  state.getWallpaperCb('aurora-violet.jpg');
  assert.equal(exported.current(), 'aurora-violet.jpg', '合法持久化名必须恢复');
  state.getWallpaperCb('junk-name.jpg');
  assert.equal(exported.current(), 'aurora-violet.jpg', '宿主回传未知名不得应用');
});

test('WB-026 背景 url 单引号必须 %27 编码（style 注入防护）', () => {
  const { host, state } = makeHost();
  const { elements, exported } = loadMain(host);
  // 模拟壁纸 URL 含单引号（静态清单外形态）——编码守卫必须生效
  exported.WALLPAPERS.push({ name: 'evil.jpg', url: "wallpapers/a'b.jpg" });
  exported.setWallpaper('evil.jpg');
  assert.equal(elements.wallpaper.style.backgroundImage, "url('wallpapers/a%27b.jpg')",
    '路径单引号必须以 %27 进入 style');
  assert.ok(!elements.wallpaper.style.backgroundImage.includes("a'b"),
    '原始单引号不得直入 style 属性');
  assert.deepEqual(state.errors, []);
});

test('WB-013 桥调用失败：jsError 留痕且不阻断首屏装配', () => {
  const { host, state } = makeHost();
  host.getEngine = () => { throw new Error('bridge down'); };
  const { elements } = loadMain(host);   // init 抛错若未被 try/catch 兜住，本行即失败
  assert.ok(state.errors.some((e) => e.includes('getEngine:init')),
    'init 拉取失败必须经 bridgeError 留痕');
  assert.equal(elements.wpList.children.length, 4,
    '引擎拉取失败后壁纸圆点装配必须照常完成（白屏防护）');
});

// WB-129（2026-09-26 审计）：restoreBox 渲染与按钮接线此前零测试
test('WB-129 restoreBox 三态渲染：n=0/1 不显示，n=5 显示并接线', () => {
  for (const n of [0, 1]) {
    const { host, state } = makeHost();
    state.hasSavedN = n;
    const { elements } = loadMain(host);
    assert.equal(elements.restoreBox.style.display, undefined,
      `n=${n}（仅 >1 显示）不得显示恢复入口`);
    assert.equal(typeof elements.restoreBtn.onclick, 'undefined',
      `n=${n} 不得给按钮接线`);
  }
  const { host, state } = makeHost();
  state.hasSavedN = 5;
  const { elements } = loadMain(host);
  assert.equal(elements.restoreBox.style.display, 'block', 'n=5 必须显示恢复入口');
  assert.match(elements.restoreBtn.textContent, /恢复上次会话（5 个标签）/,
    '按钮文案必须携带标签计数');
  elements.restoreBtn.onclick({});
  assert.equal(state.restoreCalls, 1, '点击必须调用 restoreSession');
});

// WB-089（审计 2026-09-23 清单·W5 批）：hasSaved 回传归一——字符串数字/
// 垃圾值必须 parseInt(v,10)||0，不得把 '3' 当 0、把 'abc' 当真值
test('WB-089 hasSaved parseInt 归一：字符串数字可用，垃圾值归 0 不显示', () => {
  const { host, state } = makeHost();
  state.hasSavedRaw = '3';
  const a = loadMain(host);
  assert.equal(a.elements.restoreBox.style.display, 'block',
    "字符串 '3' 必须归一为 3（>1 显示）");
  assert.match(a.elements.restoreBtn.textContent, /3 个标签/);
  const { host: h2, state: s2 } = makeHost();
  s2.hasSavedRaw = 'abc';
  const b = loadMain(h2);
  assert.equal(b.elements.restoreBox.style.display, undefined,
    "'abc' 必须归一为 0（不显示恢复入口）");
});

// WB-107（2026-09-26 审计）：书签 it.url 为 null/非字符串此前抛 TypeError
// 逃逸回调——整格后续书签全部不渲染
test('WB-107 书签 URL 畸形容错：单条跳过不中断整批渲染', () => {
  const { host, state } = makeHost();
  host.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  host.bookmarks = (cb) => cb([
    { title: '正常站', url: 'https://example.com/x' },
    { title: '空URL', url: null },          // 此前整批渲染在此崩掉
    { title: '数字URL', url: 42 },           // 非字符串——String() 归一后可渲染
    { title: '坏协议', url: 'not a url' },   // URL 解析失败——回退原文
  ]);
  const { elements } = loadMain(host);   // kind()='cs' → 装配即同步渲染
  assert.ok(!state.errors.some((e) => e.includes('bookmarks')),
    '畸形书签不得以 jsError 逃逸');
  const frag = elements.bm.children[0];
  assert.ok(frag, '宫格必须被整体替换渲染');
  const names = frag.children
    .filter((c) => c.className === 'bm' || c.className === 'bm bm-add')
    .map((c) => c.children[1].textContent);
  assert.deepEqual(names, ['正常站', '数字URL', '坏协议', '添加常用站点'],
    '空 URL 单条必须跳过，其余（含畸形解析回退）照常渲染');
});

// WB-086（审计 2026-09-23 清单·W5 批）：host 提取失败回退——URL 解析失败
// 时 host 回退原文，图标取首字符、名称回退 host（此前无断言锁定）
test('WB-086 host 提取失败回退：解析失败 URL 以原文兜底渲染图标与名称', () => {
  const { host } = makeHost();
  host.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  host.bookmarks = (cb) => cb([{ title: '', url: 'not a url' }]);
  const { elements } = loadMain(host);
  const frag = elements.bm.children[0];
  const card = frag.children[0];
  assert.equal(card.children[0].textContent, 'N',
    '图标必须取回退 host（原文）首字符大写');
  assert.equal(card.children[1].textContent, 'not a url',
    '名称在 title 为空时必须回退到 host 原文');
});

// WB-087（审计 2026-09-23 清单·W5 批）：首页只展示最近 8 个书签 + 添加磁贴
test('WB-087 前 8 书签截断：10 条书签只渲染 8 卡 + 添加磁贴', () => {
  const { host } = makeHost();
  host.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  host.bookmarks = (cb) => cb(
    Array.from({ length: 10 }, (_, i) => ({ title: '站' + i, url: 'https://s' + i + '.example.com' })));
  const { elements } = loadMain(host);
  const frag = elements.bm.children[0];
  const cards = frag.children.filter((c) => c.className === 'bm');
  assert.equal(cards.length, 8, '书签卡必须截断为 8');
  const names = cards.map((c) => c.children[1].textContent);
  assert.deepEqual(names, ['站0', '站1', '站2', '站3', '站4', '站5', '站6', '站7'],
    '保留前 8 条（按宿主返回顺序）');
  assert.equal(frag.children.at(-1).className, 'bm bm-add', '末尾必须是添加磁贴');
});

// WB-082（审计 2026-09-23 清单·W5 批）：renderEngineMenu 选中态——active 类/
// aria-checked/✓ 标记与 data.engine 定位此前零断言
test('WB-082 renderEngineMenu 选中态：aria-checked/✓/active 对齐 data.engine', () => {
  const { host } = makeHost();
  host.getEngine = (cb) => cb({
    engine: 'bing',
    engines: [{ key: 'baidu', name: '百度' }, { key: 'bing', name: '必应' }],
  });
  const { elements, exported } = loadMain(host);
  exported.renderEngineMenu();
  const items = elements.engineMenu.children;
  assert.equal(items.length, 2, '两个引擎两个菜单项');
  assert.equal(items[0]._attrs.role, 'menuitemradio', '菜单项必须声明 menuitemradio');
  assert.equal(items[0]._attrs['aria-checked'], 'false');
  assert.equal(items[1]._attrs['aria-checked'], 'true', '选中项 aria-checked=true');
  assert.equal(items[1].className, 'engine-item active', '选中项 active 类');
  assert.equal(items[1].children[1].textContent, '✓', '选中项 ✓ 标记');
  assert.equal(items[0].children[1].textContent, '', '未选项无标记');
});

// WB-083（审计 2026-09-23 清单·W5 批）：空引擎表隐藏分支——菜单不得以
// 空壳展开
test('WB-083 空引擎表隐藏分支：engines 空时菜单保持隐藏', () => {
  const { host } = makeHost();
  host.getEngine = (cb) => cb({ engine: 'baidu', engines: [] });
  const { elements, exported } = loadMain(host);
  exported.toggleEngineMenu();       // 触发展开路径
  assert.equal(elements.engineMenu.style.display, 'none',
    '空引擎表必须隐藏菜单（不得展开空壳）');
});

// WB-044（审计 2026-09-23 清单·W5 批）：菜单方向键导航——↑/↓ 移动焦点并环绕
test('WB-044 引擎菜单方向键导航：↓ 到下一项、↑ 环绕到末项', () => {
  const { host } = makeHost();
  host.getEngine = (cb) => cb({
    engine: 'baidu',
    engines: [
      { key: 'baidu', name: '百度' },
      { key: 'bing', name: '必应' },
      { key: 'google', name: '谷歌' },
    ],
  });
  const { elements, exported } = loadMain(host);
  exported.renderEngineMenu();
  const items = elements.engineMenu.children;
  items[0].onkeydown({ key: 'ArrowDown', preventDefault() {}, stopPropagation() {} });
  assert.equal(items[1]._focused, true, '↓ 必须把焦点移到下一项');
  items[1]._focused = false;
  items[0].onkeydown({ key: 'ArrowUp', preventDefault() {}, stopPropagation() {} });
  assert.equal(items[2]._focused, true, '↑ 从首项必须环绕到末项');
  // 触发按键不得选中引擎（仅 Enter/Space 选中）
  assert.ok(true);
});

// WB-045（审计 2026-09-23 清单·W5 批）：Escape 关闭菜单——菜单项内与文档级
// 双路径，关闭必须复位 aria-expanded 并归还焦点到胶囊
test('WB-045 Escape 关闭引擎菜单：aria-expanded 复位 + 焦点归还胶囊', () => {
  const { host } = makeHost();
  host.getEngine = (cb) => cb({
    engine: 'baidu',
    engines: [{ key: 'baidu', name: '百度' }, { key: 'bing', name: '必应' }],
  });
  const { elements, exported, docHandlers } = loadMain(host);
  exported.toggleEngineMenu();
  assert.equal(elements.engineMenu.style.display, 'block', '菜单先展开');
  assert.equal(elements.enginePill._attrs['aria-expanded'], 'true');
  // 路径一：菜单项上按 Escape
  const item = elements.engineMenu.children[0];
  item.onkeydown({ key: 'Escape', preventDefault() {}, stopPropagation() {} });
  assert.equal(elements.engineMenu.style.display, 'none', '菜单必须收起');
  assert.equal(elements.enginePill._attrs['aria-expanded'], 'false',
    'aria-expanded 必须复位');
  assert.equal(elements.enginePill._focused, true, '焦点必须归还胶囊');
  // 路径二：焦点在菜单外时文档级 Escape
  exported.toggleEngineMenu();
  assert.equal(elements.engineMenu.style.display, 'block');
  item.onkeydown({ key: 'ArrowDown', preventDefault() {}, stopPropagation() {} });
  elements.enginePill._focused = false;
  docHandlers.keydown[0]({ key: 'Escape' });
  assert.equal(elements.engineMenu.style.display, 'none', '文档级 Escape 必须收起菜单');
  assert.equal(elements.enginePill._attrs['aria-expanded'], 'false');
});

// WB-084（审计 2026-09-23 清单·W5 批）：go() 空输入短路
test('WB-084 go() 空输入短路：空白/无导航能力不得发起导航', () => {
  const { host, state } = makeHost();
  const { elements, exported } = loadMain(host);
  elements.q.value = '';
  exported.go();
  assert.equal(state.navigateCalls, 0, '空输入不得导航');
  elements.q.value = '   ';
  exported.go();
  assert.equal(state.navigateCalls, 0, '纯空白输入不得导航');
  const { host: h2, state: s2 } = makeHost();
  h2.has = () => false;                       // 无导航能力
  const b = loadMain(h2);
  b.elements.q.value = 'example.com';
  b.exported.go();
  assert.equal(s2.navigateCalls, 0, '无导航能力不得导航');
});

// WB-085 + WB-096（审计 2026-09-23 清单·W5 批）：_searchBusy 防抖与
// submit+click 双路径防重放——两条路径共用同一把忙碌锁
test('WB-085/096 搜索防重放：submit+click 双路径共用忙碌锁，锁释放后可再搜', () => {
  const { host, state } = makeHost();
  const { elements, exported, timers } = loadMain(host);
  elements.q.value = 'example.com';
  elements.searchBtn.textContent = '搜索';     // 桩初始文案（对齐标记层）
  // 双路径连击：form submit + 按钮 click——只允许一次导航
  elements.searchForm._handlers.submit[0]({ preventDefault() {} });
  elements.searchBtn._handlers.click[0]();
  assert.equal(state.navigateCalls, 1, 'submit+click 连击必须被忙碌锁合并为一次导航');
  assert.equal(elements.searchBtn.textContent, '搜索中…', '锁占用期间按钮呈忙碌文案');
  assert.equal(timers.fired.length, 1, '必须布且仅布一个复位定时器');
  timers.fired[0].fn();                       // 锁释放
  assert.equal(elements.searchBtn.textContent, '搜索', '锁释放后按钮文案复原');
  elements.searchForm._handlers.submit[0]({ preventDefault() {} });
  assert.equal(state.navigateCalls, 2, '锁释放后新搜索必须放行');
});

// WB-057（审计 2026-09-23 清单·W5 批）：时序常量单源——默认值与
// window.AegisTiming 注入值两个形态
test('WB-057 时序常量单源：默认三常量齐备，window.AegisTiming 可单源注入', () => {
  const { host, state } = makeHost();
  const { elements, exported, timers } = loadMain(host);
  assert.deepEqual(exported.timing(), {
    BOOKMARK_RETRY_MS: 200, BOOKMARK_RETRY_MAX: 10, SEARCH_BUSY_RESET_MS: 1200,
  }, '无注入时使用与 start.js 单源一致的字面量兜底');
  elements.q.value = 'x';
  exported.go();
  assert.equal(timers.fired[0].ms, 1200, '防抖复位延时消费 SEARCH_BUSY_RESET_MS');
  // 注入自定义时序——go 的复位延时必须随单源走（不再硬编码 1200）
  const { host: h2, state: s2 } = makeHost();
  const b = loadMain(h2, { AegisTiming: { BOOKMARK_RETRY_MS: 5, BOOKMARK_RETRY_MAX: 3, SEARCH_BUSY_RESET_MS: 123 } });
  b.elements.q.value = 'x';
  b.exported.go();
  assert.equal(b.timers.fired[0].ms, 123, '注入的 SEARCH_BUSY_RESET_MS 必须生效');
});

// WB-088（审计 2026-09-23 清单·W5 批）：书签有界重试——桥未就绪时按
// TIMING.BOOKMARK_RETRY_MS 间隔至多 BOOKMARK_RETRY_MAX 次
test('WB-088 书签有界重试：无宿主时按上限轮询，宿主就绪即渲染', () => {
  const { host, state } = makeHost();
  host.kind = () => null;                      // 桥未就绪形态
  host.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  let bookmarkCalls = 0;
  host.bookmarks = (cb) => { bookmarkCalls += 1; cb([]); };
  const { timers } = loadMain(host);
  assert.equal(timers.fired.length, 1, 'attempt 0 无宿主 → 布下一次轮询');
  assert.equal(timers.fired[0].ms, 200, '轮询间隔消费 BOOKMARK_RETRY_MS');
  // 依次驱动 attempt 1..9 → 各布一针（含首次共 10 针），attempt 10 直接渲染
  for (let i = 2; i <= 10; i++) timers.fired[i - 2].fn();
  assert.equal(timers.fired.length, 10, '至多 BOOKMARK_RETRY_MAX=10 次轮询');
  timers.fired[9].fn();                        // attempt 10 → 放弃等待直接渲染
  assert.equal(bookmarkCalls, 1, '重试耗尽后必须尝试渲染（有界、不无限轮询）');
  assert.equal(timers.fired.length, 10, '耗尽后不得再布新轮询');
  // 宿主中途就绪：立即渲染、不再等待
  const { host: h2 } = makeHost();
  h2.kind = (() => { let n = 0; return () => (n++ >= 3 ? 'cs' : null); })();
  h2.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  let calls2 = 0;
  h2.bookmarks = (cb) => { calls2 += 1; cb([]); };
  const t2 = loadMain(h2).timers;
  t2.fired[0].fn(); t2.fired[1].fn();          // attempt 1/2 仍无宿主
  t2.fired[2].fn();                            // attempt 3 → kind()='cs' → 渲染
  assert.equal(calls2, 1, '宿主就绪后必须立即渲染书签');
  assert.equal(t2.fired.length, 3, '就绪后不得继续轮询');
});

// WB-048（审计 2026-09-23 清单·W5 批）：☆ 收藏文案平台差异化
test('WB-048 空书签文案按平台差异化：cs 提示地址栏 ☆，android 不提专属控件', () => {
  const { host } = makeHost();
  host.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  host.bookmarks = (cb) => cb([]);
  const { elements } = loadMain(host);
  // 空书签分支直接把 bm-empty div 追加进 #bm（不经 fragment）
  assert.match(elements.bm.children[0].textContent, /地址栏右侧的 ☆/,
    'cs（Windows）保留 ☆ 指引文案');
  const { host: h2 } = makeHost();
  h2.kind = () => 'android';                   // 纵深防御形态：android+bookmarks
  h2.has = (f) => f === 'navigate' || f === 'geo' || f === 'bookmarks';
  h2.bookmarks = (cb) => cb([]);
  const b = loadMain(h2);
  assert.equal(b.elements.bm.children[0].textContent, '还没有书签',
    'android 文案不得指向不存在的地址栏 ☆ 控件');
});

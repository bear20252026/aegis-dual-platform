// start_main.test.mjs —— start.main.js 壁纸行为回归（node --test）
// WB-025：未知壁纸必须整体 no-op（不得污染当前壁纸/样式/桥调用）；
// WB-026：背景 url('...') 单引号必须 %27 编码（style 注入防护）；
// WB-013：桥调用失败必须经 jsError 留痕且不阻断首屏装配。
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
    _textContent: '',
    appendChild(c) { node.children.push(c); return c; },
    // WB-107：书签宫格经 replaceChildren 整段替换（frag 进容器）
    replaceChildren(...cs) { node.children.length = 0; cs.forEach((c) => node.children.push(c)); },
    addEventListener(type, fn) { (node._handlers[type] = node._handlers[type] || []).push(fn); },
    focus() {},
    setAttribute() {},
    getAttribute() { return null; },
  };
  // 真实 DOM 语义：对 textContent 赋值会清空全部子节点（容器换页依赖）
  Object.defineProperty(node, 'textContent', {
    get() { return node._textContent; },
    set(v) { node._textContent = String(v); node.children.length = 0; },
  });
  return node;
}

function makeHost() {
  const state = { setCalls: [], errors: [], getWallpaperCb: null, hasSavedN: 0, restoreCalls: 0 };
  const host = {
    kind: () => 'cs',
    has: (f) => f === 'navigate' || f === 'geo',   // bookmarks=false → 书签宫格早退
    getEngine: (cb) => cb({ engine: 'baidu', engines: [{ key: 'baidu', name: '百度' }] }),
    getWallpaper: (cb) => { state.getWallpaperCb = cb; },
    hasSaved: (cb) => cb(state.hasSavedN),
    restoreSession: () => { state.restoreCalls += 1; },
    setWallpaper: (name) => state.setCalls.push(name),
    jsError: (...a) => state.errors.push(a.join(' ')),
    navigate: () => {},
  };
  return { host, state };
}

function loadMain(host) {
  const elements = {
    engineName: el('span'),
    engineMenu: el('div'),
    wallpaper: el('div'),
    wpList: el('div'),
    bm: el('div'),
    restoreBox: el('div'),
    restoreBtn: el('button'),
  };
  const document = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => el(tag),
    // WB-107：书签整段构建走 DocumentFragment
    createDocumentFragment: () => ({ children: [], appendChild(c) { this.children.push(c); } }),
    addEventListener() {},
    activeElement: null,
  };
  const win = { addEventListener() {} };
  let exported = null;
  // 模块级 var/函数声明是 Function 体局部——尾部追加 __take 导出待测面
  new Function('document', 'window', 'Host', '__take',
    MAINJS + '\n;__take({ setWallpaper: setWallpaper, WALLPAPERS: WALLPAPERS, ' +
    'current: function () { return current; } });')(
    document, win, host, (x) => { exported = x; });
  return { elements, exported };
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

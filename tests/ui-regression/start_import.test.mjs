// start_import.test.mjs —— start.import.js 导入向导行为回归（node --test）
// WB-015：导入统计管道（Promise 返回值 → 聚合 → 完成页）此前零回归——
//   WB-001 修复（统计恒 0/0）后无测试兜底；
// WB-020：15s 扫描超时兜底此前零回归——宿主无响应时向导永久卡死；
// WB-027：焦点管理（初始聚焦/关闭归还）行为锁定。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const IMPORT = readFileSync(join(ROOT, 'shared', 'shell', 'start.import.js'), 'utf8');

// —— 最小 DOM 桩（仅覆盖 start.import.js 触及的表面） ——
function el(tag) {
  const node = {
    tagName: tag,
    children: [],
    style: {},
    dataset: {},
    className: '',
    title: '',
    value: '',
    disabled: false,
    checked: false,
    tabIndex: 0,
    _handlers: {},
    _focused: false,
    _textContent: '',
    appendChild(c) { node.children.push(c); return c; },
    addEventListener(type, fn) { (node._handlers[type] = node._handlers[type] || []).push(fn); },
    focus() { node._focused = true; },
    setAttribute() {},
    getAttribute() { return null; },
    contains() { return true; },
    querySelectorAll() { return []; },
  };
  // 真实 DOM 语义：对 textContent 赋值会清空全部子节点——
  // renderPick/renderDone 正是靠「先清容器再追加」换页，桩必须同构
  Object.defineProperty(node, 'textContent', {
    get() { return node._textContent; },
    set(v) { node._textContent = String(v); node.children.length = 0; },
  });
  return node;
}

function click(node) {
  (node._handlers.click || []).forEach((fn) =>
    fn({ stopPropagation() {}, preventDefault() {} }));
}

// 定时器桩：只记录不调度——15s 兜底不必真等，也不会拖住测试进程
function loadImport(host) {
  const elements = {
    importModal: el('div'),
    imBody: el('div'),
    imNext: el('button'),
    imClose: el('button'),
    importEntry: el('button'),
  };
  const docHandlers = {};
  const timers = {
    fired: [],
    cleared: [],
    setTimeout(fn, ms) { timers.fired.push({ fn, ms }); return timers.fired.length; },
    clearTimeout(id) { timers.cleared.push(id); },
  };
  const document = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => el(tag),
    addEventListener(type, fn) { (docHandlers[type] = docHandlers[type] || []).push(fn); },
    activeElement: null,
  };
  new Function('document', 'Host', 'setTimeout', 'clearTimeout', IMPORT)(
    document, host, timers.setTimeout, timers.clearTimeout);
  return { elements, docHandlers, timers };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test('WB-015 导入统计管道：Promise 返回值聚合为总数（WB-001 回归兜底）', async () => {
  let scanCb = null;
  const host = {
    has: (f) => f === 'import',
    importScan: (cb) => { scanCb = cb; },
    importBookmarks: () => Promise.resolve({ imported: 3, total: 5 }),
    importHistory: () => Promise.resolve({ imported: 10, total: 20 }),
    jsError: () => {},
  };
  const { elements } = loadImport(host);
  click(elements.importEntry);                       // openWizard：扫描中
  assert.match(elements.imBody.children[0].textContent, /正在扫描/);
  scanCb([{ browser: 'chrome', bookmarks: true, history: true }]);
  assert.equal(elements.imNext.disabled, false, '扫描回来后下一步必须可用');
  click(elements.imNext);                            // runImport
  await flush(); await flush();
  const texts = elements.imBody.children.map((c) => c.textContent).join('\n');
  assert.match(texts, /导入完成：共新增 13 条（解析 25 条）。/,
    '完成页统计必须来自 Promise 返回值聚合（回调结果恒 0/0 的旧缺陷）');
  assert.match(texts, /Chrome 书签：导入 3 \/ 5/);
  assert.match(texts, /Chrome 历史：导入 10 \/ 20/);
});

test('WB-015 单来源失败计入失败数，成功来源统计不受牵连', async () => {
  let scanCb = null;
  const host = {
    has: () => true,
    importScan: (cb) => { scanCb = cb; },
    importBookmarks: (src) => src === 'edge'
      ? Promise.reject(new Error('db locked'))
      : Promise.resolve({ imported: 3, total: 5 }),
    importHistory: () => Promise.resolve({ imported: 10, total: 20 }),
    jsError: () => {},
  };
  const { elements } = loadImport(host);
  click(elements.importEntry);
  scanCb([
    { browser: 'chrome', bookmarks: true, history: true },
    { browser: 'edge', bookmarks: true, history: true },
  ]);
  // 默认只勾第一个来源（chrome）——勾上 edge 后统计须跨来源聚合
  const rows = elements.imBody.children.filter((c) => c._cb);
  assert.equal(rows.length, 4, '两个来源行 + 书签/历史行');
  assert.equal(rows[1]._browser, 'edge');
  rows[1]._cb.checked = true;
  click(elements.imNext);
  await flush(); await flush();
  const texts = elements.imBody.children.map((c) => c.textContent).join('\n');
  // chrome 3+10 成功，edge 书签拒绝（failures=1）、历史 10 成功
  assert.match(texts, /部分完成：新增 23 条（解析 45 条），1 个来源失败。/,
    '拒绝必须计入失败数且成功来源统计照常聚合');
});

test('WB-020 扫描 15s 超时兜底：宿主无响应可退出，迟到回包被忽略', () => {
  let scanCb = null;
  const host = {
    has: () => true,
    importScan: (cb) => { scanCb = cb; },   // 永不回调——桥未挂接形态
    jsError: () => {},
  };
  const { elements, timers } = loadImport(host);
  click(elements.importEntry);
  assert.match(elements.imBody.children[0].textContent, /正在扫描/);
  assert.equal(elements.imNext.disabled, true, '扫描未回前下一步必须禁用');
  assert.equal(timers.fired.length, 1, '打开向导必须布 15s 兜底定时器');
  assert.equal(timers.fired[0].ms, 15000);
  timers.fired[0].fn();                              // 15s 到点
  assert.equal(elements.imNext.disabled, false, '超时后必须放行（不再永久卡死）');
  assert.match(elements.imBody.children[0].textContent, /未检测到/);
  scanCb([{ browser: 'chrome', bookmarks: true }]);  // 迟到回包
  assert.match(elements.imBody.children[0].textContent, /未检测到/,
    '超时后迟到的扫描回包不得重绘向导');
});

test('WB-020 及时回包：兜底定时器必须被清除（无泄漏）并进入选择页', () => {
  let scanCb = null;
  const host = { has: () => true, importScan: (cb) => { scanCb = cb; }, jsError: () => {} };
  const { elements, timers } = loadImport(host);
  click(elements.importEntry);
  scanCb([{ browser: 'chrome', bookmarks: true, history: true }]);
  assert.deepEqual(timers.cleared, [timers.fired.length],
    '及时回包必须 clearTimeout 兜底定时器');
  assert.match(elements.imBody.children[0].textContent, /检测到以下来源/);
  assert.equal(elements.imBody.children[1].children[1].textContent,
    'Chrome（书签 + 历史）', '来源行文案必须含浏览器名与数据类型');
});

test('WB-020 扫描 Promise 拒绝（win 形态）→ 空结果兜底不挂死', async () => {
  const host = {
    has: () => true,
    importScan: () => Promise.reject(new Error('bridge gone')),
    jsError: () => {},
  };
  const { elements } = loadImport(host);
  click(elements.importEntry);
  await flush();
  assert.match(elements.imBody.children[0].textContent, /未检测到/,
    '扫描 Promise 拒绝必须走空结果兜底');
  assert.equal(elements.imNext.disabled, false);
});

test('WB-027 焦点管理：打开初始聚焦弹层，关闭归还触发元素', () => {
  const host = { has: () => true, importScan: (cb) => cb([]), jsError: () => {} };
  const { elements, docHandlers } = loadImport(host);
  click(elements.importEntry);
  assert.equal(elements.imClose._focused, true, '打开后初始焦点必须进弹层');
  (docHandlers.keydown || []).forEach((fn) => fn({ key: 'Escape' }));   // 关闭
  assert.equal(elements.importModal.style.display, 'none');
  assert.equal(elements.importEntry._focused, true, '焦点必须归还触发元素');
});

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

// 定时器桩：只记录不调度——15s 兜底不必真等，也不会拖住测试进程。
// W5 批（WB-057）：window 形参注入——start.import.js 的扫描超时时长收敛到
// window.AegisTiming.IMPORT_SCAN_TIMEOUT_MS 单源，桩默认空 window（兜底 15000）
function loadImport(host, winExtras) {
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
  const win = Object.assign({}, winExtras);
  new Function('document', 'window', 'Host', 'setTimeout', 'clearTimeout', IMPORT)(
    document, win, host, timers.setTimeout, timers.clearTimeout);
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

test('WB-020 扫描 Promise 拒绝（宿主返回 thenable 形态）→ 空结果兜底不挂死', async () => {
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

// WB-055（审计 2026-09-23 清单·W5 批）：未选来源/内容静默关闭 → 留在
// 选择页并给出明确提示（不丢弹层、不丢已勾选状态）
test('WB-055 未选来源点「开始导入」：弹层不关闭并提示先选择', () => {
  const host = { has: () => true, importScan: (cb) => cb([{ browser: 'chrome', bookmarks: true }]), jsError: () => {} };
  const { elements } = loadImport(host);
  click(elements.importEntry);
  const rows = elements.imBody.children.filter((c) => c._cb);
  rows.forEach((r) => { r._cb.checked = false; });   // 全部取消勾选
  click(elements.imNext);
  assert.equal(elements.importModal.style.display, 'flex', '弹层必须保持打开（此前静默关闭）');
  const texts = elements.imBody.children.map((c) => c.textContent).join('\n');
  assert.match(texts, /请先选择至少一个导入来源与内容类型/,
    '必须给出明确提示（此前无任何反馈）');
  // 内容类型未勾选同样触发提示
  rows[0]._cb.checked = true;
  const contentRows = elements.imBody.children.filter((c) => c._cb);
  contentRows.slice(1).forEach((r) => { r._cb.checked = false; });  // 取消 书签/历史
  click(elements.imNext);
  const texts2 = elements.imBody.children.map((c) => c.textContent).join('\n');
  assert.match(texts2, /请先选择至少一个导入来源与内容类型/, '仅选来源不选内容也必须提示');
});

// WB-056（审计 2026-09-23 清单·W5 批）：running 态 Escape 不再静默中断向导
test('WB-056 running 态 Escape 忽略：导入进行中不得关闭，完成后恢复可关', async () => {
  let resolveBm = null;
  const host = {
    has: () => true,
    importScan: (cb) => cb([{ browser: 'chrome', bookmarks: true }]),
    importBookmarks: () => new Promise((r) => { resolveBm = r; }),   // 悬挂——running 态
    importHistory: () => Promise.resolve({ imported: 0, total: 0 }),
    jsError: () => {},
  };
  const { elements, docHandlers } = loadImport(host);
  click(elements.importEntry);
  click(elements.imNext);                          // → running（链首环在微任务执行）
  await flush();                                   // 驱动 importBookmarks 被调用
  assert.ok(resolveBm, '导入任务必须已发起（Promise 悬挂中）');
  assert.equal(elements.imNext.disabled, true, 'running 态下一步必须禁用');
  (docHandlers.keydown || []).forEach((fn) => fn({ key: 'Escape' }));
  assert.equal(elements.importModal.style.display, 'flex',
    'running 态 Escape 必须被忽略（此前静默中断、结果丢弃）');
  resolveBm({ imported: 1, total: 1 });            // 导入完成
  await flush(); await flush();
  assert.match(elements.imBody.children[0].textContent, /导入完成/, '完成页照常渲染');
  (docHandlers.keydown || []).forEach((fn) => fn({ key: 'Escape' }));
  assert.equal(elements.importModal.style.display, 'none', 'done 态 Escape 恢复关闭');
});

// WB-090（审计 2026-09-23 清单·W5 批）：renderDone 三态文案——「导入失败」
// 态此前零断言（WB-015 仅锁成功/部分完成两态）
test('WB-090 renderDone 失败态：全部来源失败且零导入时必须呈现失败文案', async () => {
  const host = {
    has: () => true,
    importScan: (cb) => cb([{ browser: 'chrome', bookmarks: true, history: true }]),
    importBookmarks: () => Promise.reject(new Error('db locked')),
    importHistory: () => Promise.resolve({ imported: 0, total: 0 }),
    jsError: () => {},
  };
  const { elements } = loadImport(host);
  click(elements.importEntry);
  click(elements.imNext);
  await flush(); await flush();
  const texts = elements.imBody.children.map((c) => c.textContent).join('\n');
  assert.match(texts, /导入失败：1 个来源未能读取（浏览器可能正在运行或数据不可用）。/,
    '失败态不得伪装成「导入完成/部分完成」');
  assert.equal(elements.imNext.textContent, '完成');
  assert.doesNotMatch(texts, /导入完成：共新增/, '失败态不得复用成功句式');
});

// WB-092（审计 2026-09-23 清单·W5 批）：历史条数默认 500——选项默认选中
// 与 parseInt 兜底双路径此前零断言
test('WB-092 历史条数默认 500：500 选项默认选中，运行期 parseInt 兜底 500', async () => {
  let seenLimit = null;
  const host = {
    has: () => true,
    importScan: (cb) => cb([{ browser: 'chrome', bookmarks: false, history: true }]),
    importHistory: (limit) => { seenLimit = limit; return Promise.resolve({ imported: 1, total: 1 }); },
    jsError: () => {},
  };
  const { elements } = loadImport(host);
  click(elements.importEntry);
  // 选项层：500 必须是 selected 默认项
  const select = elements.imBody.children.map((c) => c.children && c.children[1])
    .find((c) => c && c.tagName === 'select');
  assert.ok(select, '必须渲染历史条数下拉');
  const options = select.children;
  assert.deepEqual(options.map((o) => o.value), ['100', '500', '1000', '2000'],
    '条数档位固定 100/500/1000/2000');
  assert.equal(options.filter((o) => o.selected).map((o) => o.value).join(','), '500',
    '默认选中 500（此前零断言）');
  // 运行层：桩 select.value 为空串 → parseInt NaN → ||500 兜底
  click(elements.imNext);
  await flush(); await flush();
  assert.equal(seenLimit, 500, '兜底路径必须落到 500');
});

// WB-057（审计 2026-09-23 清单·W5 批）：扫描超时时长消费
// window.AegisTiming.IMPORT_SCAN_TIMEOUT_MS 单源（不再硬编码 15000）
test('WB-057 扫描超时时长单源注入：window.AegisTiming 生效', () => {
  const host = { has: () => true, importScan: () => {}, jsError: () => {} };
  const { elements, timers } = loadImport(host, { AegisTiming: { IMPORT_SCAN_TIMEOUT_MS: 999 } });
  click(elements.importEntry);
  assert.equal(timers.fired.length, 1, '打开向导必须布扫描兜底定时器');
  assert.equal(timers.fired[0].ms, 999, '注入的 IMPORT_SCAN_TIMEOUT_MS 必须生效（默认 15000 由 WB-020 锁定）');
});

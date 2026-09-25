// start_host.test.mjs —— start.js Host 适配层行为回归（node --test）
// WB-021..024（审计批次W4）：适配层是三端唯一桥入口，kind()/has()/
// Android 引擎回退/csCall 响应关联此前零测试——语义漂移即三端同坏。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const HOSTJS = readFileSync(join(ROOT, 'shared', 'shell', 'start.js'), 'utf8');

// 裸标识符 pywebview/chrome 以形参遮蔽（缺席即 undefined，不抛 ReferenceError；
// winApi/andApi 的 window.xxx && 短路保证 undefined 桥不会被解引用）
function loadHost({ pywebview, AegisBridge, chrome } = {}) {
  const win = {};
  if (pywebview !== undefined) win.pywebview = pywebview;
  if (AegisBridge !== undefined) win.AegisBridge = AegisBridge;
  if (chrome !== undefined) win.chrome = chrome;
  const fn = new Function('window', 'pywebview', 'chrome', 'AegisBridge',
    HOSTJS + '\nreturn Host;');
  return fn(win, pywebview, chrome, AegisBridge);
}

// cs 桥桩：捕获 postMessage 与 message 监听，可模拟宿主按 id 回包
function csBridge() {
  const listeners = [];
  const posted = [];
  return {
    bridge: {
      webview: {
        postMessage(msg) { posted.push(msg); },
        addEventListener(_type, fn) { listeners.push(fn); },
      },
    },
    posted,
    respond(id, result) {
      listeners.forEach((fn) => fn({ data: { __aegisRes: 1, id, result } }));
    },
  };
}

test('WB-021 kind() 三端判定与共存优先级', () => {
  assert.equal(loadHost({}).kind(), null, '三桥全无 → null（bookmarks 重试依赖该语义）');
  assert.equal(loadHost({ pywebview: { api: {} } }).kind(), 'win');
  assert.equal(loadHost({ AegisBridge: {} }).kind(), 'android');
  assert.equal(loadHost({ chrome: { webview: { postMessage() {} } } }).kind(), 'cs');
  // 迁移期多桥共存时判定必须确定：win > android > cs
  const all = { pywebview: { api: {} }, AegisBridge: {}, chrome: { webview: { postMessage() {} } } };
  assert.equal(loadHost(all).kind(), 'win', 'win 桥优先级最高');
  assert.equal(loadHost({ AegisBridge: {}, chrome: { webview: { postMessage() {} } } }).kind(),
    'android', 'android 桥优先级高于 cs');
});

test('WB-022 has() 能力面白名单语义', () => {
  assert.equal(loadHost({}).has('navigate'), false, '无宿主 → 一律 false');
  const cs = loadHost({ chrome: { webview: { postMessage() {} } } });
  assert.equal(cs.has('bookmarks'), true, 'cs（正典栈）全能力');
  assert.equal(cs.has('any-unknown-feat'), true, 'win/cs 端白名单不设限');
  const and = loadHost({ AegisBridge: {} });
  ['engine', 'navigate', 'wallpaper', 'geo', 'snake'].forEach((f) =>
    assert.equal(and.has(f), true, 'android 必须声明 ' + f));
  ['bookmarks', 'import', 'restore', 'not-a-feat'].forEach((f) =>
    assert.equal(and.has(f), false, 'android 不得声明 ' + f));
});

test('WB-023 Android getEngine 解析失败/空表 → 默认引擎集回退', () => {
  const FALLBACK = {
    engine: 'baidu',
    engines: [
      { key: 'baidu', name: '百度' },
      { key: 'bing', name: '必应' },
      { key: 'google', name: '谷歌' },
      { key: 'sogou', name: '搜狗' },
    ],
  };
  const cases = [
    ['非 JSON 字符串', 'not-json{{'],
    ['engines 空表', JSON.stringify({ engine: 'baidu', engines: [] })],
    ['null 返回', null],
  ];
  for (const [name, payload] of cases) {
    const Host = loadHost({ AegisBridge: { getEngine: () => payload } });
    let got = 'unset';
    Host.getEngine((data) => { got = data; });
    assert.deepEqual(got, FALLBACK, name + ' 必须回退默认引擎集（胶囊保持可用）');
  }
});

test('WB-023 Android getEngine 合法 JSON 原样透传', () => {
  const payload = { engine: 'bing', engines: [{ key: 'bing', name: '必应' }] };
  const Host = loadHost({ AegisBridge: { getEngine: () => JSON.stringify(payload) } });
  let got = null;
  Host.getEngine((data) => { got = data; });
  assert.deepEqual(got, payload, '合法引擎表不得被回退覆盖');
});

test('WB-024 csCall 响应按 id 关联：乱序/迟到/重复/未知 id 各归其主', () => {
  const { bridge, posted, respond } = csBridge();
  const Host = loadHost({ chrome: bridge });
  const seen = [];
  Host.getEngine((r) => seen.push(['engine', r]));
  Host.getWallpaper((r) => seen.push(['wallpaper', r]));
  assert.deepEqual(posted.map((m) => m.op), ['getEngine', 'getWallpaper'], '操作按序发出');
  const [idEngine, idWp] = posted.map((m) => m.id);
  assert.notEqual(idEngine, idWp, '并发调用 id 必须唯一');
  respond(idWp, 'wp-result');                        // 乱序：先回后发的
  assert.deepEqual(seen, [['wallpaper', 'wp-result']]);
  respond(idEngine, { engine: 'baidu' });
  assert.deepEqual(seen,
    [['wallpaper', 'wp-result'], ['engine', { engine: 'baidu' }]],
    '各回包必须送达自己的回调');
  respond(idEngine, 'dup');                          // 已消费的 id
  assert.equal(seen.length, 2, '同一 id 重复回包不得二次分发');
  respond(9999, 'ghost');                            // 未知 id
  assert.equal(seen.length, 2, '未知 id 回包必须静默忽略');
});

test('WB-024 回调异常隔离：抛错不阻断后续分发且经 jsError 留痕', () => {
  const { bridge, posted, respond } = csBridge();
  const Host = loadHost({ chrome: bridge });
  let rendered = 0;
  const seen = [];
  Host.getEngine(() => { rendered += 1; throw new Error('render boom'); });
  Host.getWallpaper((r) => seen.push(r));
  respond(posted[0].id, { engines: [] });            // 回调抛错
  respond(posted[1].id, 'wp');                       // 后续回包仍须送达
  assert.equal(rendered, 1);
  assert.deepEqual(seen, ['wp'], '一个回调抛错不得吞掉其他 pending');
  const jsErr = posted.find((m) => m.op === 'jsError');
  assert.ok(jsErr, '回调异常必须经 jsError 留痕');
  assert.ok(String(jsErr.args[0]).includes('ntp callback'), '留痕须标记 ntp callback 来源');
});

test('WB-024 无 cs 桥时同步降级 cb(null)（不挂死）', () => {
  const Host = loadHost({});
  let got = 'unset';
  Host.getWallpaper((r) => { got = r; });
  assert.equal(got, null, '无桥 csCall 必须同步 cb(null)');
  assert.doesNotThrow(() => Host.setEngine('baidu'), '无 cb 调用不得抛错');
});

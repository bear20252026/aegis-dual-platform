// start_host.test.mjs —— start.js Host 适配层行为回归（node --test）
// WB-021..024（审计批次W4）：适配层是双端唯一桥入口，kind()/has()/
// Android 引擎回退/csCall 响应关联此前零测试——语义漂移即双端同坏。
// WB-114（2026-09-26 审计）：归档 pywebview 栈的 'win' 桥分支已删除——
// 三端判定收敛为 cs/android 双端，win 相关断言一并移除。
// WB-127（2026-09-26 审计）：chrome 桩抽至 helpers.mjs 共享（与
// import_contract.test.mjs 单一事实源）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadHost, makeCsBridge, HOSTJS } from './helpers.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('WB-021 kind() 双端判定与共存优先级（win 归档桥已删）', () => {
  assert.equal(loadHost({}).kind(), null, '双桥全无 → null（bookmarks 重试依赖该语义）');
  assert.equal(loadHost({ AegisBridge: {} }).kind(), 'android');
  assert.equal(loadHost({ chrome: { webview: { postMessage() {} } } }).kind(), 'cs');
  // 迁移期多桥共存时判定必须确定：android > cs
  assert.equal(loadHost({ AegisBridge: {}, chrome: { webview: { postMessage() {} } } }).kind(),
    'android', 'android 桥优先级高于 cs');
  // win 桥（pywebview）已随归档删除——注入也不再识别为宿主
  assert.equal(loadHost({ pywebview: { api: {} } }).kind(), null,
    'pywebview 归档桥不得再被识别（WB-114）');
});

test('WB-022 has() 能力面白名单语义', () => {
  assert.equal(loadHost({}).has('navigate'), false, '无宿主 → 一律 false');
  const cs = loadHost({ chrome: { webview: { postMessage() {} } } });
  assert.equal(cs.has('bookmarks'), true, 'cs（正典栈）全能力');
  assert.equal(cs.has('any-unknown-feat'), true, 'cs 端白名单不设限');
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
  const { bridge, posted, respond } = makeCsBridge();
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
  const { bridge, posted, respond } = makeCsBridge();
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

// WB-150（2026-10-01 审计）：Host.goBack 此前仅静态断言（存在性）——
// 补双端行为断言：cs 端必须按协议信封 postMessage（__aegis/id/op/args），
// android 端必须直调 AegisBridge.goBack
test('WB-150 goBack 行为：cs 端 postMessage 信封 + android 端桥直调', () => {
  const { bridge, posted } = makeCsBridge();
  const Host = loadHost({ chrome: bridge });
  Host.goBack();
  assert.equal(posted.length, 1, 'cs 端 goBack 必须发出恰好一条 postMessage');
  const msg = posted[0];
  assert.equal(msg.__aegis, 1, '请求信封必须带 __aegis 标记');
  assert.equal(msg.op, 'goBack', 'op 必须是 goBack');
  assert.deepEqual(msg.args, [], 'goBack 无参数');
  assert.ok(Number.isInteger(msg.id) && msg.id >= 1, '请求必须携带自增 id（回包关联）');
  // android 端：同步桥直调
  const calls = [];
  const Host2 = loadHost({ AegisBridge: { goBack: () => calls.push('goBack') } });
  Host2.goBack();
  assert.deepEqual(calls, ['goBack'], 'android 端必须直调 AegisBridge.goBack');
});

// WB-205（2026-10-02 审计）：error/unhandledrejection 上报通道此前零回归——
// loadHost 的 events 记录器取出 start.js 首文件注册的两个监听并受控触发
test('WB-205 全局错误上报通道：error 五参透传 + rejection 前缀 + jsError 自抛吞没', () => {
  const events = [];
  const { bridge, posted } = makeCsBridge();
  const Host = loadHost({ chrome: bridge, events });
  const onErr = events.find((e) => e.type === 'error');
  const onRej = events.find((e) => e.type === 'unhandledrejection');
  assert.ok(onErr && onRej, 'start.js 必须注册 error/unhandledrejection 两监听（WB-140 前移面）');
  // error 事件 → jsError 五参原样透传
  onErr.fn({ message: 'boom', filename: 'start.js', lineno: 7, colno: 3, error: { stack: 's1' } });
  const err = posted.filter((m) => m.op === 'jsError').at(-1);
  assert.ok(err, 'error 事件必须经 jsError 上报');
  assert.deepEqual(err.args, ['boom', 'start.js', 7, 3, 's1'],
    'message/filename/lineno/colno/stack 五参必须原样透传');
  // unhandledrejection → 「Promise rejection:」前缀 + 辅助参数置空
  onRej.fn({ reason: 'bad promise' });
  const rej = posted.filter((m) => m.op === 'jsError').at(-1);
  assert.equal(rej.args[0], 'Promise rejection: bad promise',
    'rejection 必须带 Promise rejection: 前缀');
  assert.deepEqual(rej.args.slice(1), ['', 0, 0, ''],
    'rejection 的 filename/lineno/colno/stack 按约定置空');
  // jsError 自身抛错（桥坏）必须被监听内的 try/catch 吞掉——不逃逸
  const events2 = [];
  const badHost = loadHost({
    chrome: {
      webview: {
        postMessage() { throw new Error('bridge down'); },
        addEventListener() {},
      },
    },
    events: events2,
  });
  assert.ok(events2.length >= 1, '坏桥形态下监听仍须注册');
  assert.doesNotThrow(() => {
    events2.forEach((e) => {
      if (e.type === 'error') e.fn({ message: 'x', filename: '', lineno: 0, colno: 0, error: null });
    });
  }, 'jsError 自抛必须被吞（防上报通道异常递归）');
});

// WB-037（审计 2026-09-23 清单·W5 批）：csCall pending 此前无 TTL——宿主
// 永不回包时回调条目泄漏。惰性清扫实现：每次新请求前清理超龄条目并以
// cb(null) 兜底；不引入定时器（保持「零定时器零 IO」性质——WB-128 回归锁）
test('WB-037 pending TTL：超龄条目在新请求时被清扫并 cb(null)，未超龄不受影响', () => {
  let now = 1000;
  class FakeDate extends Date {
    static now() { return now; }
  }
  const { bridge, posted, respond } = makeCsBridge();
  const Host = loadHost({ chrome: bridge, Date: FakeDate });
  const seen = [];
  Host.getWallpaper((r) => seen.push(['wp-stale', r]));     // 请求 A（永不回包）
  now += 31000;                                              // A 超过 30s TTL
  Host.getEngine((r) => seen.push(['engine-fresh', r]));     // 请求 B——触发清扫
  assert.deepEqual(seen, [['wp-stale', null]],
    '超龄 pending 必须在下一请求时以 cb(null) 兜底完成（不悬挂不泄漏）');
  assert.equal(posted.length, 2, '清扫不影响新请求照常发出');
  // 迟到回包：A 已被清扫 → 静默忽略；B 正常送达
  respond(posted[0].id, 'late-a');
  respond(posted[1].id, 'engine-ok');
  assert.deepEqual(seen, [['wp-stale', null], ['engine-fresh', 'engine-ok']],
    '已清扫条目的迟到回包必须被忽略，未超龄条目正常分发');
  // 未超龄条目（30s 内）不得被误清
  now += 20000;
  Host.getWallpaper((r) => seen.push(['wp-young', r]));
  now += 25000;   // 距上一请求 25s < TTL
  const before = seen.length;
  Host.getEngine(() => {});
  assert.equal(seen.length, before, 'TTL 内的 pending 不得被误清扫');
});

// WB-095（审计 2026-09-23 清单·W5 批）：start.js 的 Android 引擎回退表是
// 引擎名单第三份副本（C# UrlNormalizer / Android SearchEngines 之外）——
// 此前无跨端断言，名单漂移即 Android 断桥时静默回退到错误引擎集。
// 对账口径与 scripts/verify_cross_end_lists.py 一致：baidu/bing/google/sogou
// 四引擎三端完全一致；C# 扩展引擎（so360 等）须在 CS_ENGINE_EXTENSIONS
// 白名单显式登记——本断言锁定「回退表 ⊆ 三端正典名单且与 Android 全等」。
test('WB-095 Android 引擎回退表跨端一致：与 SearchEngines.kt 全等、为 UrlNormalizer.cs 子集', () => {
  const readRepo = (p) => readFileSync(join(ROOT, ...p.split('/')), 'utf8');
  const startJs = readRepo('shared/shell/start.js');
  const fbBlock = startJs.match(/function engineFallback\(\) \{[\s\S]*?\n        \}/);
  assert.ok(fbBlock, 'start.js 必须存在 engineFallback 回退表');
  const fbKeys = [...fbBlock[0].matchAll(/key: '([a-z0-9]+)'/g)].map((m) => m[1]);
  assert.deepEqual(fbKeys, ['baidu', 'bing', 'google', 'sogou'],
    '回退表必须恰好是四正典引擎（有缺或多出即 Android 断桥回退失真）');
  // Android 端 SearchEngines.kt ENGINE_URLS
  const kt = readRepo('android/app/src/main/java/com/aegis/browser/SearchEngines.kt');
  const ktBlock = kt.match(/ENGINE_URLS[\s\S]*?mapOf\(([\s\S]*?)\)/);
  assert.ok(ktBlock, 'SearchEngines.kt 必须有 ENGINE_URLS 表');
  const ktKeys = [...ktBlock[1].matchAll(/"([a-z0-9]+)" to "/g)].map((m) => m[1]);
  assert.deepEqual(ktKeys, fbKeys, 'Android ENGINE_URLS 必须与 JS 回退表完全一致');
  // C# 端 UrlNormalizer.cs EngineUrls（允许白名单扩展引擎，核心四引擎必须齐）
  const cs = readRepo('windows/src/Aegis.Windows.App/Chrome/UrlNormalizer.cs');
  const csFrom = cs.indexOf('EngineUrls');
  const csTo = cs.indexOf('EngineNames');
  assert.ok(csFrom > 0 && csTo > csFrom, 'UrlNormalizer.cs 必须有 EngineUrls 表');
  const csKeys = [...cs.slice(csFrom, csTo).matchAll(/\["([a-z0-9]+)"\] = "http/g)].map((m) => m[1]);
  for (const k of fbKeys) {
    assert.ok(csKeys.includes(k), `C# 引擎表必须包含正典引擎 ${k}`);
  }
});

// WB-053（审计 2026-09-23 清单·W5 批）：C# NtpBridge 协议 schema 对账——
// shared/jsapi-schema.ntp-bridge.cs.json（手工维护——jsapi-schema.json 由
// 生成器产出有 CI diff 门禁）的 operations 必须与 start.js 适配层的
// csCall 调用点一一对应（桥方法增删两侧同步，防协议漂移）
test('WB-053 C# 桥协议 schema：operations 与 start.js csCall 调用点一致', () => {
  const schema = JSON.parse(readFileSync(
    join(ROOT, 'shared', 'jsapi-schema.ntp-bridge.cs.json'), 'utf8'));
  const schemaOps = Object.keys(schema.operations).sort();
  const codeOps = [...HOSTJS.matchAll(/csCall\('([a-zA-Z]+)'/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(codeOps)].sort(), schemaOps,
    'start.js 的 csCall op 集合必须与 schema operations 完全一致');
  assert.ok(schemaOps.length >= 14, '正典桥 14 个操作必须全部登记');
  // 请求/响应信封字段与实现一致（csCall 发 __aegis、监听 __aegisRes）
  assert.equal(schema.transport.request.shape.__aegis, 1);
  assert.equal(schema.transport.response.shape.__aegisRes, 1);
});

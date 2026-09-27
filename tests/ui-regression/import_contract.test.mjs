// import_contract.test.mjs —— start.js Host 适配层「导入契约」回归（node --test）
// 命名口径（WB-127，2026-09-26 审计；SP-163 glob 化后改名零门禁成本）：
// 本文件锁定导入统计管道的桥契约
//（importBookmarks/importHistory/importScan），适配层通用语义（kind()/has()/
// 引擎回退/csCall 响应关联）在 start_host.test.mjs——两文件共用 helpers.mjs 桩。
// WB-001/002/WB-015：导入统计管道此前在 cs 端返回 undefined（结果只进
// 回调而 runImport 以返回值收集）——导入统计恒 0/0 且成功后宫格不刷新。
// 本文件以最小 chrome.webview 桩实际执行 start.js，锁定 Promise 契约。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHost, makeCsBridge } from './helpers.mjs';

test('WB-001 Host.importBookmarks 在 cs 端返回 Promise 并以桥结果 resolve', async () => {
  const { bridge, posted, respond } = makeCsBridge();
  const Host = loadHost({ chrome: bridge });
  const outcome = { imported: 12, total: 20, results: [] };
  const p = Host.importBookmarks('chrome');
  assert.equal(typeof p.then, 'function', 'importBookmarks 必须返回 thenable');
  const msg = posted.at(-1);
  assert.equal(msg.op, 'importBookmarks');
  respond(msg.id, outcome);
  assert.deepEqual(await p, outcome);
});

test('WB-002 Host.importHistory 在 cs 端返回 Promise 并透传 limit 参数', async () => {
  const { bridge, posted, respond } = makeCsBridge();
  const Host = loadHost({ chrome: bridge });
  const outcome = { imported: 5, total: 5, results: [] };
  const p = Host.importHistory(800, 'edge');
  const msg = posted.at(-1);
  assert.equal(msg.op, 'importHistory');
  assert.deepEqual(msg.args, [800, 'edge']);
  respond(msg.id, outcome);
  assert.deepEqual(await p, outcome);
});

test('WB-001 Android 端导入能力为空数据 Promise（不抛 TypeError）', async () => {
  const Host = loadHost({ AegisBridge: {} });  // 仅 Android 桥
  const r = await Host.importBookmarks('chrome');
  assert.deepEqual(r, { imported: 0, total: 0 });
});

// WB-128（2026-09-26 审计）：宿主无回包场景此前仅断言 typeof==='function'
//（零行为断言）——补真实行为：请求已发出、回调不被误触、迟到回包仍按
// id 送达、进程可正常退出。
test('WB-128 宿主无回包时 importScan 仍可用：请求发出且回调不被误触', () => {
  const { bridge, posted, respond } = makeCsBridge();
  const Host = loadHost({ chrome: bridge });
  let called = 0;
  assert.doesNotThrow(() => Host.importScan(() => { called += 1; }),
    '无回包调用必须同步安全返回（不抛错）');
  assert.equal(called, 0, '宿主未回包时回调不得被触发');
  const msg = posted.at(-1);
  assert.equal(msg.op, 'importScan', 'importScan 必须经 cs 桥发出请求');
  respond(msg.id, [{ browser: 'chrome', bookmarks: true }]);
  assert.equal(called, 1, '迟到回包仍须按 id 送达回调（pending 不丢）');
});

test('WB-128 csCall 零定时器零 IO：无回包不阻断测试进程退出', () => {
  // 「进程可正常退出」的结构性依据：csCall 的 pending 表是纯对象（无
  // 定时器/无 IO 句柄），未决回调不持有事件循环——本套件能自然结束即
  // 该性质的直接证据；此处再锁行为面：无桥降级同步 cb(null) 不挂死。
  const Host = loadHost({});
  let got = 'unset';
  Host.importScan((r) => { got = r; });
  assert.equal(got, null, '无桥时必须同步 cb(null)（不挂死等待）');
});

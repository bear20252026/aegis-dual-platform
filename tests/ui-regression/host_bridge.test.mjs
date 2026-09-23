// host_bridge.test.mjs —— start.js Host 适配层行为级回归（node --test）
// WB-001/002/WB-015：导入统计管道此前在 cs 端返回 undefined（结果只进
// 回调而 runImport 以返回值收集）——导入统计恒 0/0 且成功后宫格不刷新。
// 本文件以最小 chrome.webview 桩实际执行 start.js，锁定 Promise 契约。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const HOSTJS = readFileSync(join(ROOT, 'shared', 'shell', 'start.js'), 'utf8');

function loadHostCs() {
  const listeners = [];
  const posted = [];
  const webview = {
    postMessage(msg) { posted.push(msg); },
    addEventListener(_type, fn) { listeners.push(fn); },
  };
  const sandboxWindow = { chrome: { webview: webview } };
  // csApi 引用裸 `chrome` 全局——以同名形参遮蔽 Node 环境
  const fn = new Function('window', 'chrome', HOSTJS + '\nreturn Host;');
  const Host = fn(sandboxWindow, sandboxWindow.chrome);
  return {
    Host,
    posted,
    // 模拟宿主回包（csCall 关联 id 分发）
    respond(id, result) {
      listeners.forEach((fn2) => fn2({ data: { __aegisRes: 1, id, result } }));
    },
  };
}

test('WB-001 Host.importBookmarks 在 cs 端返回 Promise 并以桥结果 resolve', async () => {
  const h = loadHostCs();
  const outcome = { imported: 12, total: 20, results: [] };
  const p = h.Host.importBookmarks('chrome');
  assert.equal(typeof p.then, 'function', 'importBookmarks 必须返回 thenable');
  const msg = h.posted.at(-1);
  assert.equal(msg.op, 'importBookmarks');
  h.respond(msg.id, outcome);
  assert.deepEqual(await p, outcome);
});

test('WB-002 Host.importHistory 在 cs 端返回 Promise 并透传 limit 参数', async () => {
  const h = loadHostCs();
  const outcome = { imported: 5, total: 5, results: [] };
  const p = h.Host.importHistory(800, 'edge');
  const msg = h.posted.at(-1);
  assert.equal(msg.op, 'importHistory');
  assert.deepEqual(msg.args, [800, 'edge']);
  h.respond(msg.id, outcome);
  assert.deepEqual(await p, outcome);
});

test('WB-001 Android 端导入能力为空数据 Promise（不抛 TypeError）', async () => {
  const webviewLike = undefined;
  const sandboxWindow = { AegisBridge: {} };  // 仅 Android 桥
  const fn = new Function('window', HOSTJS + '\nreturn Host;');
  const Host = fn(sandboxWindow);
  const r = await Host.importBookmarks('chrome');
  assert.deepEqual(r, { imported: 0, total: 0 });
});

test('WB-001 宿主无回包时 importScan 仍可用（回归 baseline：csCall 不挂死新契约）', () => {
  const h = loadHostCs();
  assert.equal(typeof h.Host.importScan, 'function');
});

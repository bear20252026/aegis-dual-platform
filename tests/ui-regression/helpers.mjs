// helpers.mjs —— tests/ui-regression 共享桩（WB-127，2026-09-26 审计）
// 此前 host_bridge（现 import_contract）.test.mjs 与 start_host.test.mjs 各自维护一套
// chrome.webview 桩（两份重复、语义易漂移）——抽单一事实源：
// - loadHost：以形参遮蔽裸标识符加载 shared/shell/start.js（无桥即 undefined，
//   不抛 ReferenceError；winApi/andApi 的 window.xxx && 短路同理）
// - makeCsBridge：捕获 postMessage 与 message 监听，可按 id 模拟宿主回包
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

export const HOSTJS = readFileSync(join(ROOT, 'shared', 'shell', 'start.js'), 'utf8');

/**
 * 以可控的全局桥注入执行 start.js，返回 Host 适配层。
 * pywebview/AegisBridge/chrome 缺席即 undefined（桥不存在语义）。
 * Date（WB-037，2026-09-23 审计·W5 批）：可选注入假时钟构造器——
 * csCall 的惰性 TTL 清扫以 Date.now() 取时，测试用假时钟驱动超龄。
 */
export function loadHost({ pywebview, AegisBridge, chrome, Date: DateCtor } = {}) {
  const win = {};
  if (pywebview !== undefined) win.pywebview = pywebview;
  if (AegisBridge !== undefined) win.AegisBridge = AegisBridge;
  if (chrome !== undefined) win.chrome = chrome;
  const fn = new Function('window', 'pywebview', 'chrome', 'AegisBridge', 'Date',
    HOSTJS + '\nreturn Host;');
  return fn(win, pywebview, chrome, AegisBridge, DateCtor || Date);
}

/**
 * cs 桥桩：返回 { bridge, posted, respond }。
 * - bridge.chromium.webview 形态注入 loadHost({ chrome: bridge })
 * - posted 记录全部 postMessage 载荷（op/id/args）
 * - respond(id, result) 按 csCall 的 id 关联模拟宿主回包
 */
export function makeCsBridge() {
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

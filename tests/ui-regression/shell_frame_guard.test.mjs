// shell_frame_guard.test.mjs —— AX-03（外部第三轮审计 2026-10-11）：壳页 CSP 的
// 帧许可必须显式关闭。
//
// 为什么这属于安全判据而不是排版细节：Android 的宿主桥只能证明「顶层文档是谁」
// （AegisBridge 读 webView.getUrl，@JavascriptInterface 拿不到调用者所在 frame 的
// Origin）。今天 `shared/shell` 零 iframe ⇒ 顶层 URL 恰好等于唯一可能的调用者；
// 但那是**巧合级**成立——`default-src 'self'` 隐含 `frame-src 'self'`，任何人把
// default-src 调宽、或往壳页里加一个同源 frame，桥的归属判据就悄悄变成「用顶层
// URL 冒充帧身份」。显式 `frame-src 'none'` 把这件事从「顺带放大」变成「必须评审」。
//
// 与 WB-105 的分工：那条判的是 frame-ancestors **不得**出现在 meta CSP（规范里
// meta 会忽略它＝安全声明失真）。本文件判的是 frame-src **必须**出现——两者是
// 取回类指令与嵌入类指令的差别，写在一起才不会被下一个人当成矛盾。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SHELL = join(ROOT, 'shared', 'shell');
const HTML = readFileSync(join(SHELL, 'start.html'), 'utf8');

/** 有界取 CSP 正文：只认这一条 meta，不做全文扫描。 */
function cspOf(html) {
  const match = html.match(/http-equiv="Content-Security-Policy"\s*\n?\s*content="([^"]*)"/);
  assert.ok(match, 'start.html 必须存在 CSP meta——没有它下面每条断言都是空转');
  return match[1];
}

test('CSP 显式声明 frame-src none（不再由 default-src 隐含）', () => {
  assert.match(cspOf(HTML), /(^|;)\s*frame-src 'none'\s*(;|$)/,
    "frame-src 必须显式为 'none'：壳页任何 frame 都会让桥的顶层 URL 判据失真（AX-03）");
});

test('正向控制：解析到的确实是要判的那份 CSP', () => {
  // 「不含禁止形态」的断言在空串上恒真——先证明这份 CSP 里既有本批加的指令，
  // 也有它周围那一圈既有许可（少一条说明匹配跑到了别处）。
  const csp = cspOf(HTML);
  for (const directive of [
    "default-src 'self'",
    "script-src 'self' file:",
    "img-src 'self' file: data:",
    "connect-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ]) {
    assert.ok(csp.includes(directive), `CSP 缺既有指令「${directive}」——本文件的解析面已漂移`);
  }
});

test('frame-src 在位而 frame-ancestors 仍不得回归（WB-105 的那半边）', () => {
  const csp = cspOf(HTML);
  assert.ok(!/frame-ancestors/.test(csp),
    'meta CSP 里的 frame-ancestors 会被引擎忽略＝安全声明失真（WB-105）');
  assert.ok(/frame-src/.test(csp),
    'frame-src 是取回类指令、meta 下确实生效——与 frame-ancestors 不是一回事');
});

test('今日成本为零：壳页四段脚本与 HTML 都不建 iframe', () => {
  // 这条同时是「为什么可以现在关掉」的证据与「将来谁改了会被拦」的哨兵。
  const sources = ['start.html', 'start.js', 'start.main.js', 'start.snake.js', 'start.import.js']
    .map((name) => readFileSync(join(SHELL, name), 'utf8'))
    .join('\n')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
  assert.ok(!/<iframe/i.test(sources), '壳页不得出现 <iframe 标签');
  assert.ok(!/createElement\(\s*['"]iframe['"]\s*\)/i.test(sources),
    "壳页不得动态创建 iframe——frame-src 'none' 与它二者只能留一个");
});

test('这份 CSP 确实随包进 Android（assets 源目录指向 shared/shell）', () => {
  // 「共享壳层」不等于「两端都吃到」：Android 是把整个目录当 assets 打进 APK 的，
  // srcDir 一改，本文件判的语料就不再是出货的那份。
  const gradle = readFileSync(join(ROOT, 'android', 'app', 'build.gradle.kts'), 'utf8');
  assert.match(gradle, /assets\.srcDir\(rootProject\.file\("\.\.\/shared\/shell"\)\)/,
    'Android assets 必须仍取自 shared/shell——否则 CSP 改动不随包（AX-03 的前提）');
});

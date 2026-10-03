// WB-195（2026-10-02 审计）：跨端桥 op 词表对账——start.js 发出的每个 op
// 必须在两端宿主有真实落点，否则 WebView2 侧新增 op 漏宿主 case 时静默走
// TTL cb(null) 兜底（WB-037），30s 后 UI 无响应且门禁零信号。
//
// 对账面（三份源码逐个正则提取——任何一端改动漂移即本测试红）：
// - JS → C# 通道：start.js 的 csCall('<op>' 字面量 ↔ NtpBridge.cs 的
//   Dispatch case 标签（双向全等——漏 case 与死 case 都是契约漂移）；
// - JS → Android 通道：start.js 的 andApi() 短路分支 a.<method>( 直调 ↔
//   AegisHomeBridge.kt 的 @JavascriptInterface 方法（宿主 ⊇ 调用集——
//   Android 侧允许存在页面尚未消费的入口级方法）。
//
// 反腐烂锚：四个集合任一提取为空/低于历史规模即红——正则因重构失配时
// 绝不允许静默通过（空集 ⊊ 任何集合的空洞真值）。

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const START_JS = readFileSync(join(ROOT, 'shared', 'shell', 'start.js'), 'utf8');
const NTP_BRIDGE_CS = readFileSync(
  join(ROOT, 'windows', 'src', 'Aegis.Windows.App', 'Chrome', 'Ntp', 'NtpBridge.cs'),
  'utf8',
);
const HOME_BRIDGE_KT = readFileSync(
  join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'AegisHomeBridge.kt'),
  'utf8',
);

const uniq = (list) => [...new Set(list)];

// JS → C# 通道 op 词表（csCall('<op>' 字面量——start.js 是唯一发出点）
const csOps = uniq([...START_JS.matchAll(/csCall\('([a-zA-Z]+)'/g)].map((m) => m[1]));
// JS → Android 通道 op 词表（andApi() 短路分支上的 a.<method>( 直调——
// start.js 内 `a.` 前缀仅桥调用使用，正则提取实测零误报）
const androidOps = uniq([...START_JS.matchAll(/\ba\.([a-zA-Z]+)\(/g)].map((m) => m[1]));
// C# 宿主 case 标签（NtpBridge.Dispatch）
const csCases = uniq([...NTP_BRIDGE_CS.matchAll(/case "([a-zA-Z]+)"/g)].map((m) => m[1]));
// Android 宿主 @JavascriptInterface 方法名（注解与 fun 间允许 KDoc/注解行——
// 从注解位置向后 200 字符窗内取首个 fun 名）
const ktMethods = [];
for (const m of HOME_BRIDGE_KT.matchAll(/@JavascriptInterface/g)) {
  const f = HOME_BRIDGE_KT.slice(m.index, m.index + 200).match(/fun\s+([a-zA-Z]+)/);
  if (f) ktMethods.push(f[1]);
}
const ktFuns = uniq(ktMethods);

test('WB-195 反腐烂锚：四集合提取非空且不低于历史规模', () => {
  assert.ok(csOps.length >= 14, `csCall op 提取异常（${csOps.length} < 14）——正则/源码结构漂移`);
  assert.ok(csCases.length >= 14, `NtpBridge case 提取异常（${csCases.length} < 14）`);
  assert.ok(androidOps.length >= 8, `android 桥调用提取异常（${androidOps.length} < 8）`);
  assert.ok(ktFuns.length >= 8, `@JavascriptInterface 方法提取异常（${ktFuns.length} < 8）`);
});

test('WB-195：JS cs 通道 op 与 NtpBridge.cs case 双向全等', () => {
  const missing = csOps.filter((op) => !csCases.includes(op));
  assert.deepEqual(
    missing,
    [],
    `start.js 发出但 NtpBridge.cs 无 case 的 op（将静默 TTL cb(null)）：${missing.join(', ')}`,
  );
  const dead = csCases.filter((op) => !csOps.includes(op));
  assert.deepEqual(
    dead,
    [],
    `NtpBridge.cs 存在但 start.js 从未发出的 case（死分支）：${dead.join(', ')}`,
  );
});

test('WB-195：JS android 通道调用 ⊆ AegisHomeBridge @JavascriptInterface 方法', () => {
  const missing = androidOps.filter((op) => !ktFuns.includes(op));
  assert.deepEqual(
    missing,
    [],
    `start.js 直调但 AegisHomeBridge 未暴露的方法（页面收到 undefined）：${missing.join(', ')}`,
  );
});

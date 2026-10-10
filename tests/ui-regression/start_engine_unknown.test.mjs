// start_engine_unknown.test.mjs —— R9-SH-8（第九轮 2026-10-10）：引擎胶囊的
// 「宿主未回包」状态必须可见且留痕。
//
// 被消除的形态：init 路径 `Host.getEngine(function (data) { if (!data) return; … })`
// 对 null 回包**静默退出**——胶囊停在 start.html 硬编码的「百度」上且零痕迹，用户以为
// 设置生效；而 null 是可达路径（桥未挂接时 csCall 直接 cb(null)；宿主永不回包时
// WB-037 的 TTL 清扫也 cb(null) 兜底）。对照 WB-138 已为书签做的 null/[] 分流。
//
// 刻意**不**猜一个默认引擎：真实默认可能是 bing，猜错会把搜索发去错引擎——
// 所以只把状态显式化（「未知」）并经 bridgeError 留痕。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MAINJS, loadMain, makeHost } from './helpers.mjs';

// start.html:38 的初始标签——预置它才能证「过期标签被换掉」而不是「从没写过」。
const HTML_LABEL = { engineName: { textContent: '百度' } };

function hostReturning(payload) {
  const { host, state } = makeHost();
  host.getEngine = (cb) => cb(payload);
  return { host, state };
}

test('宿主回 null：胶囊显式「未知」并留痕，不再停在硬编码标签上', () => {
  const { host, state } = hostReturning(null);
  const { elements } = loadMain(host, undefined, HTML_LABEL);
  assert.equal(elements.engineName.textContent, '未知',
    'null 回包必须把可见状态改成「未知」（旧行为：保持「百度」且零痕迹）');
  assert.ok(state.errors.some((e) => e.includes('getEngine:init')),
    `必须经 jsError 留痕，实得 ${JSON.stringify(state.errors)}`);
});

test('宿主回空引擎表：同样不显示过期标签（renderEngine 的空表分支）', () => {
  const { host } = hostReturning({ engine: 'baidu', engines: [] });
  const { elements } = loadMain(host, undefined, HTML_LABEL);
  assert.equal(elements.engineName.textContent, '未知',
    'ENGINES 为空时旧行为也是「什么都不写」——胶囊继续谎报当前引擎');
});

test('对照组：正常回包照常渲染引擎名（修复不得把健康路径判成未知）', () => {
  const { host, state } = hostReturning({
    engine: 'bing',
    engines: [{ key: 'baidu', name: '百度' }, { key: 'bing', name: '必应' }],
  });
  const { elements } = loadMain(host, undefined, HTML_LABEL);
  assert.equal(elements.engineName.textContent, '必应');
  assert.deepEqual(state.errors, [], '健康路径不得留痕');
});

test('反向锚：把 null 分支改回静默 return，症状必须重现（证明上面两条判据真的在判它）', () => {
  // 内存态注入，不动工作树：还原旧写法后「未知」与留痕都不再发生。
  const mutated = MAINJS.replace(
    "if (!data) { bridgeError('getEngine:init', 'null'); renderEngine(true); return; }",
    "if (!data) return;");
  assert.notEqual(mutated, MAINJS, '注入点失配——反向锚本身失效');
  const { host, state } = hostReturning(null);
  const { elements } = loadMain(host, undefined, HTML_LABEL, mutated);
  assert.equal(elements.engineName.textContent, '百度', '旧写法下硬编码标签原样留着（这就是被消除的形态）');
  assert.deepEqual(state.errors, [], '旧写法零留痕');
});

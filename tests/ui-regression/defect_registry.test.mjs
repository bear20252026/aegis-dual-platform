// defect_registry.test.mjs —— 缺陷库与测试引用互检（lint 测试）
// SP-044（审计 2026-09-23 清单·SP1 批）：tests/KNOWN_DEFECTS.md 主表与
// tests/ui-regression 断言面此前无互检——两类漂移均已实际发生：
//   ① "登记无断言"（WB-064/SP-039：BUG-009 被 start.main.js 注释引用却无登记行；
//      SP-040：BUG-014 被 start_page.test.mjs 断言引用却无登记行）
//   ② "断言无登记"（本测试反向面——断言引用的 BUG 必须先登记）
// 双向锁定：任一侧增删不同步即本门禁红。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const KNOWN = readFileSync(join(ROOT, 'tests', 'KNOWN_DEFECTS.md'), 'utf8');

// 只认主表行（行首 "| BUG-NNN |"）——正文/注记中的历史提及不算登记
const registered = [...KNOWN.matchAll(/^\|\s*(BUG-\d{3})\s*\|/gm)].map((m) => m[1]);

const TEST_DIR = join(ROOT, 'tests', 'ui-regression');
const testFiles = readdirSync(TEST_DIR)
  .filter((f) => f.endsWith('.test.mjs') && f !== 'defect_registry.test.mjs');
const referenced = new Map(); // BUG-NNN -> [引用文件...]
for (const f of testFiles) {
  const text = readFileSync(join(TEST_DIR, f), 'utf8');
  for (const m of text.matchAll(/BUG-\d{3}/g)) {
    if (!referenced.has(m[0])) referenced.set(m[0], []);
    if (!referenced.get(m[0]).includes(f)) referenced.get(m[0]).push(f);
  }
}

test('SP-044 ①缺陷库登记行必须在 ui-regression 有断言引用', () => {
  assert.ok(registered.length >= 13, `缺陷库主表登记行应 ≥ 13，实际 ${registered.length}`);
  const missing = registered.filter((id) => !referenced.has(id));
  assert.deepEqual(missing, [],
    '以下缺陷已登记但断言面零引用（回归保护缺失——补断言或说明）');
});

test('SP-044 ②断言面引用的 BUG 必须在缺陷库登记', () => {
  const orphans = [...referenced.keys()].filter((id) => !registered.includes(id));
  assert.deepEqual(orphans, [],
    '以下 BUG 被断言引用但未登记（先登记后断言——BUG-009/014 教训）');
});

test('SP-044 ③登记行无重复（编号唯一）', () => {
  const dupes = registered.filter((id, i) => registered.indexOf(id) !== i);
  assert.deepEqual(dupes, [], '缺陷库主表存在重复登记编号');
});

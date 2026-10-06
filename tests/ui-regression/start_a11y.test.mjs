// start_a11y.test.mjs —— 无障碍触控面与强制配色（R8-SH-13 / R8-SH-14，第八轮 2026-10-06）
//
// 为什么不加进 start_page.test.mjs：该文件是 490 行的零余量 ratchet 基线
// （`scripts/check_file_sizes.py` 增一行即红）——按本仓既有口径「新断言外迁成新文件」，
// 新文件进 `tests/ui-regression/*.test.mjs` 这个 glob 即进 CI 门禁（SP-163）。
//
// 两条既有回归锁（start_page.test.mjs 的 WB-141/WB-142）判的是「规则**存在**」，
// 抓不到本批修的两个真实缺口：
//   R8-SH-13 触控目标只抬了 min-height:40px，**宽度**从未纳入 ⇒ ≤640px 的 .wp
//            仍是 28px 宽（28×40），且 `.engine-item` 菜单行完全不在面内；
//   R8-SH-14 forced-colors 只关掉压暗遮罩 `#wallpaper::after`，壁纸**照片本身**
//            没中性化 ⇒ 高对比模式下 CanvasText 直接压在任意亮度照片上。
// 两者都是「beta 冒烟（首页正常渲染）看不见、真机高对比/触屏才暴露」的形态。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'shared', 'shell', 'start.css'),
  'utf8',
);

function mediaBlock(atRule) {
  const start = CSS.indexOf(atRule);
  assert.ok(start > 0, `${atRule} 媒体查询必须存在`);
  const next = CSS.indexOf('@media', start + atRule.length);
  return CSS.slice(start, next === -1 ? CSS.length : next);
}

test('R8-SH-13 触控目标是 44×44 双向保底，不是只抬高度', () => {
  const coarse = mediaBlock('@media (pointer: coarse)');
  // 高度面：菜单行 .engine-item 与遮罩按钮 .veil-btn 必须在内（此前零覆盖）
  for (const sel of ['.wp', '.quick-btn', '.search button', '.engine-pill',
    '.engine-item', '.veil-btn']) {
    assert.ok(coarse.includes(sel), `${sel} 必须纳入触控目标保底`);
  }
  assert.doesNotMatch(
    coarse, /\.wp[^{]*\{[^}]*min-height:40px/, '触控面不得回落到 40px（WCAG 2.5.5 是 44）');
  // 宽度面：圆形壁纸选择器在 ≤640px 是 28px 宽，只加 min-height 等于没修
  assert.match(coarse, /\.wp\s*\{[^}]*width:44px/, '.wp 必须有 44px 宽度保底');
  assert.match(coarse, /min-width:44px/, '胶囊/按钮必须有宽度保底（长条文案之外也不小于 44）');
});

test('R8-SH-14 forced-colors 必须连壁纸照片一起交还系统色', () => {
  const fc = mediaBlock('@media (forced-colors: active)');
  // 只写 #wallpaper::after 的旧形态：遮罩关了、照片还在 ⇒ 文字压在照片上
  const wallpaperRule = /#wallpaper\s*(?:,[^{}]*)?\s*\{[^}]*background:\s*Canvas/.exec(fc);
  assert.ok(
    wallpaperRule,
    '#wallpaper 本体必须在 forced-colors 下取 Canvas（仅关 ::after 遮罩不构成修复）',
  );
  assert.match(fc, /#wallpaper::after\s*\{[^}]*background:\s*none/, '遮罩仍须显式关闭');
});

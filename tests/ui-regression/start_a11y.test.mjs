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
//
// 第九轮 R9-SH-2 修的是**这把锁自己**：原 `mediaBlock()` 把「媒体块」切成「本 at-rule
// 到下一个 @media」——5313/19189 字符的越块切片，块外的 `.veil-btn {`（:324）与
// `.engine-item:focus-visible`（:353）都混了进来，且不剔注释（块内注记原文就写着
// `.engine-item`）。于是「本块含 .engine-item」这条断言可以在块内**根本没有**它的时候
// 成立——把 R8-SH-13 的修复从 :248 的选择器列表里摘掉，这把锁与旧的 WB-142 双双仍绿。
// 现在：① 切片按花括号配对取闭合块，② 全程在**去注释后**的文本上判，③ 判据抽成
// problemsFor(css) 以便做反向锚（本仓固定口径：不光证「现在绿」，还要证「弄坏它会红」）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'shared', 'shell', 'start.css'),
  'utf8',
);

/** 注释不参与判定：块内注记原文就写着被断言的选择器名（R9-SH-2 的漏判来源之一）。 */
const CODE = CSS.replace(/\/\*[\s\S]*?\*\//g, '');

/** 取某个 at-rule 的**闭合块**（含 at-rule 本体）：先去注释，再按花括号配对切。
    剔注释放在函数内部而不是调用点——否则喂进原文的变异用例（下面几条反向锚）会绕过它。 */
function mediaBlock(atRule, source = CSS) {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '');
  const start = code.indexOf(atRule);
  assert.ok(start > 0, `${atRule} 媒体查询必须存在`);
  const open = code.indexOf('{', start);
  let depth = 0;
  let end = -1;
  for (let i = open; i < code.length; i++) {
    if (code[i] === '{') {
      depth += 1;
    } else if (code[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i + 1;
        break;
      }
    }
  }
  assert.ok(end > open, `${atRule} 花括号未闭合——切片口径失效`);
  return code.slice(start, end);
}

/** 触控面判据（返回问题清单，空 = 通过）。抽出来是为了能把「回退半个修复」喂进来判红。 */
function touchProblems(css) {
  const coarse = mediaBlock('@media (pointer: coarse)', css);
  const problems = [];
  for (const sel of ['.wp', '.quick-btn', '.search button', '.engine-pill',
    '.engine-item', '.veil-btn']) {
    if (!coarse.includes(sel)) {
      problems.push(`${sel} 不在 coarse 触控保底的选择器列表内`);
    }
  }
  if (/\.wp[^{]*\{[^}]*min-height:40px/.test(coarse)) {
    problems.push('触控面回落到 40px（WCAG 2.5.5 是 44）');
  }
  if (!/\.wp\s*\{[^}]*width:44px/.test(coarse)) {
    problems.push('.wp 缺 44px 宽度保底（只抬高度等于没修）');
  }
  if (!/min-width:44px/.test(coarse)) {
    problems.push('胶囊/按钮缺宽度保底');
  }
  return problems;
}

/** 强制配色判据：壁纸照片本体必须交还系统色，只关遮罩不算修好。 */
function forcedColorsProblems(css) {
  const fc = mediaBlock('@media (forced-colors: active)', css);
  const problems = [];
  if (!/#wallpaper\s*(?:,[^{}]*)?\s*\{[^}]*background:\s*Canvas/.test(fc)) {
    problems.push('#wallpaper 本体未取 Canvas（仅关 ::after 遮罩不构成修复）');
  }
  if (!/#wallpaper::after\s*\{[^}]*background:\s*none/.test(fc)) {
    problems.push('遮罩未显式关闭');
  }
  return problems;
}

test('R8-SH-13 触控目标是 44×44 双向保底，不是只抬高度', () => {
  assert.deepEqual(touchProblems(CSS), []);
});

test('R8-SH-14 forced-colors 必须连壁纸照片一起交还系统色', () => {
  assert.deepEqual(forcedColorsProblems(CSS), []);
});

// ===== R9-SH-2：切片面自身的锚（不越块、不含注释——否则上面两把锁又会被块外文本喂绿）

test('mediaBlock 的切片只在闭合括号内，且不携带注释', () => {
  const coarse = mediaBlock('@media (pointer: coarse)');
  assert.ok(coarse.endsWith('}'), '切片必须以本块闭合括号结尾');
  assert.ok(!coarse.includes('/*'), '切片不得携带注释（注记里写着选择器名会喂判据）');
  // 这三条都在 coarse 块**之后**定义（:324 / :334 / :349 附近），出现即说明越块
  for (const outside of ['.veil-btn:hover', '.snake-foot', '.engine-item:focus-visible']) {
    assert.ok(!coarse.includes(outside), `切片越块：命中块外内容 ${outside}`);
  }
  assert.ok(coarse.length < 1200, `coarse 块异常膨胀（${coarse.length} 字符）——切片面失控`);
});

test('切片口径与块内实际内容一致：块外补的选择器不算覆盖', () => {
  // `.engine-item` / `.veil-btn` 只在 coarse 块内出现在 :248 那条保底列表里——把它们从
  // **那一行**摘掉必须判红。同一份回退在旧口径（切到下一个 @media）下是绿的：块外的
  // `.engine-item:focus-visible`（:353）与 `.veil-btn {`（:324）会替它顶过断言，
  // 下面第二段就是把这件事钉成文字（旧口径的切片确实含这两个名字）。
  const narrowed = CSS.replace(
    '.wp, .quick-btn, .search button, .engine-pill, .engine-item, .veil-btn {',
    '.wp, .quick-btn, .search button, .engine-pill {',
  );
  assert.notEqual(narrowed, CSS, '注入锚点失配——反向用例自己会恒绿');
  const problems = touchProblems(narrowed);
  assert.ok(
    problems.some((p) => p.includes('.engine-item')) && problems.some((p) => p.includes('.veil-btn')),
    `摘掉保底选择器后仍判通过：${JSON.stringify(problems)}`,
  );
  // 同一份回退在**未修切片**的旧口径下是绿的——这条就是 R9-SH-2 报的失效形态，
  // 因此必须能构造出来：用「切到下一个 @media」的旧切片判同一份 CSS。
  const legacyStart = CODE.indexOf('@media (pointer: coarse)');
  const legacySlice = CODE.slice(
    legacyStart,
    CODE.indexOf('@media', legacyStart + '@media (pointer: coarse)'.length),
  );
  assert.ok(legacySlice.includes('.engine-item') && legacySlice.includes('.veil-btn'),
    '旧口径的越块切片本应仍然包含这两个名字（否则本条反向锚没有证明任何东西）');
});

test('forced-colors 只关遮罩时必须判红', () => {
  const halfFixed = CSS.replace(/#wallpaper\s*(,[^{}]*)?\s*\{([^}]*background:\s*Canvas[^}]*)\}/, '');
  assert.notEqual(halfFixed, CSS, '注入锚点失配');
  assert.ok(
    forcedColorsProblems(halfFixed).some((p) => p.includes('#wallpaper')),
    '去掉壁纸本体后仍判通过',
  );
});

test('触控面把宽度改回 28px 时必须判红', () => {
  const narrowed = CSS.replace('.wp { width:44px; height:44px; }', '.wp { height:44px; }');
  assert.notEqual(narrowed, CSS, '注入锚点失配');
  assert.ok(
    touchProblems(narrowed).some((p) => p.includes('宽度')),
    '宽度保底被摘掉后仍判通过',
  );
});

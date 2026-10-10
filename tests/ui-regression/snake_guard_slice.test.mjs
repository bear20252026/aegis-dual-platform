// snake_guard_slice.test.mjs —— 第九轮 R9-SH-4（P3，实测）：贪吃蛇键盘守卫的**切片口径**。
//
// 原断言在 start_page.test.mjs:403 是
//     SNAKE.substring(SNAKE.indexOf("document.addEventListener('keydown'"))
// 两重空心化：① `indexOf` 失配返回 -1，而 `substring(-1)` 按 0 处理 ⇒ 退化成全文扫描；
// ② 从锚点一路切到文件末尾 ⇒ 只要 `if (!isOpen) return;` 在**任意**位置出现就通过。
// 而 `start.snake.js` 里那条短路出现两次（键盘守卫 :453、触摸守卫 :472）⇒ 实测删掉键盘
// 守卫那一处，旧断言照样绿。
//
// 本文件不复述那条断言，而是把它改成「有界切片 + 反向锚」：切片必须有界（本处注册到它的
// 收尾 `});`）、必须去注释（守卫自己的注记原文写着 `ov.style.display === 'none'`，
// 不剔注释就会把历史表述当成回归——这条是同批实测撞出来的），并且**删掉守卫必须判红**
// （本仓对新锁的固定要求，R7-TOOL-04 / R8-PY-02）。
//
// 为什么不就地改 start_page.test.mjs：它是 490 行的零余量 ratchet 基线（增一行即红），
// 而加边界断言正好要增行 ⇒ 按既有口径把新判据外迁成新文件（glob 内即进 CI 门禁）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const SNAKE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'shared', 'shell', 'start.snake.js'),
  'utf8',
);

const KEYDOWN_ANCHOR = "document.addEventListener('keydown'";

/** 去注释：块注释与整行行注释都去掉（注记里会引用被禁的历史写法原文）。 */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
}

/** keydown 注册的有界片段：从注册语句到它的收尾 `});`，且只在去注释文本上判。 */
function keydownGuard(source) {
  const code = stripComments(source);
  const at = code.indexOf(KEYDOWN_ANCHOR);
  assert.ok(at > 0, `${KEYDOWN_ANCHOR} 必须存在——切片锚点失配时判据要自己响`);
  const end = code.indexOf('});', at);
  assert.ok(end > at, 'keydown 注册必须有收尾——切片不能一路读到文件末尾');
  return code.slice(at, end + 3);
}

test('WB-133 键盘守卫：keydown 注册体内必须以模块级 isOpen 短路', () => {
  const guard = keydownGuard(SNAKE);
  assert.match(guard, /if \(!isOpen\) return;/, 'isOpen 短路必须在 keydown 处理器体内');
  assert.ok(!guard.includes("ov.style.display === 'none'"),
    '守卫不得回退到「内联 display === none」判定（浮层首开前内联是空串）');
});

test('R9-SH-4 反向锚：删掉键盘守卫里的 isOpen 短路，有界切片必须判红', () => {
  const stripped = SNAKE.replace('if (!isOpen) return;', 'if (false) return;');
  assert.notEqual(stripped, SNAKE, '注入锚点失配——反向用例自己会恒绿');
  assert.ok(!/if \(!isOpen\) return;/.test(keydownGuard(stripped)),
    '键盘守卫体内的短路被删后，有界切片里不应再出现它（出现即说明切到了触摸守卫那一处）');
});

test('R9-SH-4 反向锚：旧口径（无界 substring）对同一删改仍然放行', () => {
  // 这条不是判据，而是把失效形态钉成文字：证明旧写法等于没有判据。
  const stripped = SNAKE.replace('if (!isOpen) return;', 'if (false) return;');
  const code = stripComments(stripped);
  const legacy = code.substring(code.indexOf(KEYDOWN_ANCHOR));
  assert.match(legacy, /if \(!isOpen\) return;/,
    '旧口径应仍然“通过”——它命中的是触摸守卫 :472 那一处，即全文/无界扫描的漏判');
});

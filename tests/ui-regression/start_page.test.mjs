// start_page.test.mjs —— shared/shell/start.html UI 回归测试
// 每个断言对应一个已修复缺陷（缺陷库见 tests/KNOWN_DEFECTS.md）。
// 运行：node --test tests/ui-regression/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SHELL = join(ROOT, 'shared', 'shell');
const HTML = readFileSync(join(SHELL, 'start.html'), 'utf8');
// 抽取 <script> 体做语法与内容断言
const scriptBody = HTML.match(/<script>([\s\S]*)<\/script>/)?.[1] ?? '';

function syntaxOk(body) {
  // 去宿主对象引用后应可解析（宿主对象运行时由两端注入）
  new Function(body.replace(/window\.pywebview/g, 'window.__h1__')
                   .replace(/window\.AegisBridge/g, 'window.__h2__'));
  return true;
}

test('BUG-001 启动闪退：不得用 generateViewId 作 setTag key（WeakHashMap 注册表）', () => {
  assert.ok(!/setTag\(/.test(scriptBody), 'start.html 不应包含 setTag 调用');
});

test('BUG-002 搜索 IME 失效：form submit + type=search + enterkeyhint 必须存在', () => {
  assert.match(HTML, /<form id="searchForm"/, '搜索框必须有 form 容器（IME action 触发路径）');
  assert.match(HTML, /onsubmit="event\.preventDefault\(\); go\(\);"/, 'submit 必须走 go()');
  // BUG-009：file:// 页面的 form submit 可能不触发 onsubmit——按钮必须
  // 同时保留 onclick 直调路径（双保险，修后再次失效的教训）
  assert.match(HTML, /id="searchBtn" onclick="go\(\)"/, '搜索按钮必须 onclick 直调 go()');
  assert.match(HTML, /type="search"/, 'input 必须是 search 型（键盘出「搜索」键）');
  assert.match(HTML, /enterkeyhint="search"/, '必须声明 enterkeyhint');
});

test('BUG-011/012: 双端统一——首页返回按钮 + 贪吃蛇游戏（单源 start.html）', () => {
  // BUG-012：Android 首页曾无返回入口（返回键只在 Win 原生工具栏）——
  // start.html 必须自带返回按钮，经 Host.goBack 分发双端
  assert.match(HTML, /back-fab[^>]*onclick="Host\.goBack\(\)"/, '首页必须有返回按钮并经 Host.goBack 分发');
  assert.match(HTML, /goBack: function \(\)/, 'Host 适配层必须有 goBack（Win→go_back / Android→goBack）');
  // BUG-011：贪吃蛇曾为 Android 地址栏独占（Win 完全没有）——首页单源内置
  assert.match(HTML, /id="snakeBtn"[^>]*onclick="openSnake\(\)"/, '首页必须有贪吃蛇入口按钮');
  assert.match(HTML, /id="snakeCanvas"/, '必须有贪吃蛇画布');
  assert.match(HTML, /touchmove[\s\S]{0,80}preventDefault/, '画布必须拦截 touchmove（否则滑动触发页面滚动）');
  assert.match(HTML, /Host\.has\('snake'\)/, '贪吃蛇入口必须走能力面声明');
  // BUG-014 版本替换：全屏网格页 + 最高分持久化；旧地址栏版必须移除
  assert.match(HTML, /id="snakeBest"/, '必须有最高分显示');
  assert.match(HTML, /snakeBest'/, '最高分必须持久化（localStorage，降级内存）');
  assert.match(HTML, /flex-direction:column; align-items:center; justify-content:center;/, '覆盖层必须全屏页面化');
  const snakeKt = join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'AddressBarSnake.kt');
  assert.ok(!existsSync(snakeKt), '旧版地址栏贪吃蛇（AddressBarSnake.kt）必须已删除');
  const mainKt = readFileSync(join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'MainActivity.kt'), 'utf8');
  assert.ok(!/AddressBarWithSnake/.test(mainKt), 'MainActivity 不得残留旧版调用');
});

test('BUG-003 搜索框 UI 错乱：#searchForm 必须承担 flex 行布局', () => {
  assert.match(HTML, /#searchForm\s*\{[^}]*display:flex/, 'form 打断外层 flex 的回归');
  assert.match(HTML, /#searchForm\s*\{[^}]*flex:1/, 'form 必须占满行宽');
});

test('BUG-004 首页壁纸 404：壁纸文件必须随单源目录存在且引用为相对路径', () => {
  const wpDir = join(SHELL, 'wallpapers');
  assert.ok(existsSync(wpDir), 'wallpapers 目录必须存在');
  const files = readdirSync(wpDir);
  assert.ok(files.length >= 4, `壁纸至少 4 张，实际 ${files.length}`);
  for (const f of files) {
    assert.match(HTML, new RegExp(`wallpapers/${f}`), `壁纸 ${f} 必须被 start.html 引用`);
  }
});

test('BUG-005 离线画板：按钮 + 桥调用 + 双端打包配置必须齐备', () => {
  assert.match(HTML, /id="geoBtn"/, '画板按钮必须存在');
  assert.match(HTML, /Host\.openGeo\(/, '按钮必须走 Host.openGeo 适配层');
  assert.match(HTML, /id="geoBtn"[^>]*title="离线几何画板/, '按钮须标注离线语义');
  // Windows 打包链
  const spec = readFileSync(join(ROOT, 'legacy', 'windows-pywebview', 'aegis_webview.spec'), 'utf8');
  assert.match(spec, /geogebra/, 'Windows spec 必须条件打包 geogebra');
  // Android 打包链（M-4 后经复合 action——单源无漂移）
  const wf = readFileSync(join(ROOT, '.github', 'workflows', 'release-android.yml'), 'utf8');
  assert.match(wf, /uses: \.\/\.github\/actions\/prepare-geogebra/,
    'Android 构建必须引用 prepare-geogebra 复合 action（此前内联步骤静默缺失导致按钮失效）');
  assert.match(wf, /dest-dir: android\/app\/src\/main\/assets\/geogebra/, 'dest-dir 必须指向 APK assets');
  const action = readFileSync(join(ROOT, '.github', 'actions', 'prepare-geogebra', 'action.yml'), 'utf8');
  assert.match(action, /GeoGebra\.html'; assert/, '复合 action 入口断言必须存在（fail-closed）');
  const wfw = readFileSync(join(ROOT, '.github', 'workflows', 'release-windows.yml'), 'utf8');
  assert.match(wfw, /uses: \.\/\.github\/actions\/prepare-geogebra/, 'Windows 构建同样必须引用复合 action');
});

test('BUG-006 allowedOriginRules 全域通配崩溃：不得出现 "https://*" 规则', () => {
  assert.ok(!/setOf\("https:\/\/\*", "http:\/\/\*"\)/.test(scriptBody), '通配规则回归');
});

test('BUG-007 移动端布局：viewport meta 必须存在', () => {
  assert.match(HTML, /<meta name="viewport" content="width=device-width/);
});

test('BUG-008 宿主桥单源：12+ 调用点必须收敛 Host 适配层，无 pywebview 直调', () => {
  assert.ok(!/pywebview\.api\./.test(scriptBody), '发现 pywebview 直调残留');
  assert.match(HTML, /var Host = /, 'Host 适配层必须存在');
  assert.match(HTML, /window\.AegisBridge \|\| null/, 'Android 桥必须被适配层覆盖');
  ['jsError', 'navigate', 'setWallpaper', 'getWallpaper', 'openGeo', 'has'].forEach(fn => {
    assert.match(HTML, new RegExp(`Host\\.${fn}\\(`), `Host.${fn} 必须被使用`);
  });
});

test('语法完整性：脚本体必须可解析（防 UI 白屏）', () => {
  assert.ok(syntaxOk(scriptBody));
});

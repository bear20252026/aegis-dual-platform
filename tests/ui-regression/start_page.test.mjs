// start_page.test.mjs —— shared/shell/ 单源首页 UI 回归测试
// 每个断言对应一个已修复缺陷（缺陷库见 tests/KNOWN_DEFECTS.md）。
// 运行：node --test tests/ui-regression/
// A8 拆分跟进（全面审计 2026-09-04）：start.html 已拆为 html + start.css +
// start.snake.js + start.import.js——断言目标随内容迁移到对应单源文件。
// I83 收口（2026-09-10）：内联脚本/内联事件处理器全部外置为 start.js
//（Host 适配层）与 start.main.js（主逻辑+静态绑定），CSP script-src 'self'。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SHELL = join(ROOT, 'shared', 'shell');
const HTML = readFileSync(join(SHELL, 'start.html'), 'utf8');
const CSS = readFileSync(join(SHELL, 'start.css'), 'utf8');
const HOSTJS = readFileSync(join(SHELL, 'start.js'), 'utf8');
const MAINJS = readFileSync(join(SHELL, 'start.main.js'), 'utf8');
const SNAKE = readFileSync(join(SHELL, 'start.snake.js'), 'utf8');
const IMPORT = readFileSync(join(SHELL, 'start.import.js'), 'utf8');
// 全部脚本源（内联块已外置——BUG-001/006/008 的"无残留"断言覆盖四个文件）
const allScripts = HOSTJS + '\n' + MAINJS + '\n' + SNAKE + '\n' + IMPORT;

function syntaxOk(body) {
  // 去宿主对象引用后应可解析（宿主对象运行时由两端注入）
  new Function(body.replace(/window\.pywebview/g, 'window.__h1__')
                   .replace(/window\.AegisBridge/g, 'window.__h2__'));
  return true;
}

test('BUG-001 启动闪退：不得用 generateViewId 作 setTag key（WeakHashMap 注册表）', () => {
  assert.ok(!/setTag\(/.test(allScripts), 'shell 脚本不应包含 setTag 调用');
});

test('BUG-002 搜索 IME 失效：form submit + type=search + enterkeyhint 必须存在', () => {
  assert.match(HTML, /<form id="searchForm"/, '搜索框必须有 form 容器（IME action 触发路径）');
  // I83 外置后：submit 与按钮双路径绑定在 start.main.js（addEventListener）
  assert.match(MAINJS, /getElementById\('searchForm'\)[\s\S]{0,200}addEventListener\('submit'[\s\S]{0,120}go\(\)/,
    'submit 必须走 go()');
  // BUG-009：file:// 页面的 form submit 可能不触发——按钮必须
  // 同时保留 click 直调路径（双保险，修后再次失效的教训）
  assert.match(MAINJS, /getElementById\('searchBtn'\)[\s\S]{0,200}addEventListener\('click'[\s\S]{0,120}go\(\)/,
    '搜索按钮必须 click 直调 go()');
  assert.match(HTML, /type="search"/, 'input 必须是 search 型（键盘出「搜索」键）');
  assert.match(HTML, /enterkeyhint="search"/, '必须声明 enterkeyhint');
});

test('BUG-011/012: 双端统一——返回形态统一 + 贪吃蛇游戏（单源首页）', () => {
  // BUG-012 演进（三端返回形态统一 95d9bac）：首页不再自带悬浮返回按钮——
  // 返回统一由平台 chrome 承担（Win 工具栏 / Android 系统返回键）。断言
  // 残留已清（HTML/JS 均无 back-fab）且 Host.goBack 适配能力保留。
  assert.ok(!/back-fab/.test(HTML + CSS), 'back-fab 悬浮按钮残留应已清理');
  assert.match(HOSTJS, /goBack: function \(\)/, 'Host 适配层必须有 goBack（Win→go_back / Android→goBack）');
  // BUG-011：贪吃蛇曾为 Android 地址栏独占（Win 完全没有）——首页单源内置
  assert.match(HTML, /id="snakeBtn"/, '首页必须有贪吃蛇入口按钮');
  assert.match(MAINJS, /getElementById\('snakeBtn'\)[\s\S]{0,200}addEventListener\('click'/, '入口按钮必须绑定（外置后无内联 onclick）');
  assert.match(HTML, /id="snakeCanvas"/, '必须有贪吃蛇画布');
  // A8 拆分后：画布行为/持久化/能力面调用在 start.snake.js，全屏样式在 start.css
  assert.match(SNAKE, /touchmove[\s\S]{0,80}preventDefault/, '画布必须拦截 touchmove（否则滑动触发页面滚动）');
  assert.match(SNAKE, /Host\.has\('snake'\)/, '贪吃蛇入口必须走能力面声明');
  // BUG-014 版本替换：全屏网格页 + 最高分持久化；旧地址栏版必须移除
  assert.match(HTML, /id="snakeBest"/, '必须有最高分显示');
  assert.match(SNAKE, /snakeBest'/, '最高分必须持久化（localStorage，降级内存）');
  assert.match(CSS, /flex-direction:column; align-items:center; justify-content:center;/, '覆盖层必须全屏页面化');
  const snakeKt = join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'AddressBarSnake.kt');
  assert.ok(!existsSync(snakeKt), '旧版地址栏贪吃蛇（AddressBarSnake.kt）必须已删除');
  const mainKt = readFileSync(join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'MainActivity.kt'), 'utf8');
  assert.ok(!/AddressBarWithSnake/.test(mainKt), 'MainActivity 不得残留旧版调用');
});

test('BUG-003 搜索框 UI 错乱：#searchForm 必须承担 flex 行布局', () => {
  // A8 拆分后：布局样式单源在 start.css
  assert.match(CSS, /#searchForm\s*\{[^}]*display:flex/, 'form 打断外层 flex 的回归');
  assert.match(CSS, /#searchForm\s*\{[^}]*flex:1/, 'form 必须占满行宽');
});

test('BUG-004 首页壁纸 404：壁纸文件必须随单源目录存在且引用为相对路径', () => {
  const wpDir = join(SHELL, 'wallpapers');
  assert.ok(existsSync(wpDir), 'wallpapers 目录必须存在');
  const files = readdirSync(wpDir);
  assert.ok(files.length >= 4, `壁纸至少 4 张，实际 ${files.length}`);
  for (const f of files) {
    assert.match(MAINJS, new RegExp(`wallpapers/${f}`), `壁纸 ${f} 必须被 start.main.js 引用`);
  }
});

test('BUG-005 离线画板：按钮 + 桥调用 + 双端打包配置必须齐备', () => {
  assert.match(HTML, /id="geoBtn"/, '画板按钮必须存在');
  assert.match(MAINJS, /Host\.openGeo\(/, '按钮必须走 Host.openGeo 适配层');
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
  assert.ok(!/setOf\("https:\/\/\*", "http:\/\/\*"\)/.test(allScripts), '通配规则回归');
});

test('BUG-007 移动端布局：viewport meta 必须存在', () => {
  assert.match(HTML, /<meta name="viewport" content="width=device-width/);
});

test('BUG-008 宿主桥单源：12+ 调用点必须收敛 Host 适配层，无 pywebview 直调', () => {
  assert.ok(!/pywebview\.api\./.test(allScripts), '发现 pywebview 直调残留');
  assert.match(HOSTJS, /var Host = /, 'Host 适配层必须存在');
  assert.match(HOSTJS, /window\.AegisBridge \|\| null/, 'Android 桥必须被适配层覆盖');
  ['jsError', 'navigate', 'setWallpaper', 'getWallpaper', 'openGeo', 'has'].forEach(fn => {
    assert.match(allScripts, new RegExp(`Host\\.${fn}\\(`), `Host.${fn} 必须被使用`);
  });
});

test('I83 CSP 前置：脚本全外置 + 禁内联 + connect-src none', () => {
  // 内联 <script>（无 src）不得存在——script-src 'self' 下不可执行
  assert.ok(!/<script>/.test(HTML), '不得存在内联 <script> 块（CSP 下不执行——白屏回归）');
  // 内联事件处理器属性不得存在（onclick/onsubmit/onkeydown= …）
  assert.ok(!/\son(click|submit|keydown|load|error|input|change|mouseover)=/.test(HTML),
    '不得存在内联事件处理器属性');
  // CSP meta：script-src 'self'（禁内联）、connect-src 'none'（页面零网络请求）
  assert.match(HTML, /http-equiv="Content-Security-Policy"[^>]*script-src 'self'/, '必须声明 script-src self');
  assert.match(HTML, /http-equiv="Content-Security-Policy"[^>]*connect-src 'none'/, '必须声明 connect-src none');
  // 内联 style 属性不得存在（style-src 'self' 同理）
  assert.ok(!/\sstyle="/.test(HTML), '不得存在内联 style 属性');
});

test('语法完整性：全部脚本体必须可解析（防 UI 白屏）', () => {
  // I83 外置后：Host 适配层 + 主逻辑 + snake + import 四个文件分别解析
  assert.ok(syntaxOk(HOSTJS), 'start.js 语法错误');
  assert.ok(syntaxOk(MAINJS), 'start.main.js 语法错误');
  assert.ok(syntaxOk(SNAKE), 'start.snake.js 语法错误');
  assert.ok(syntaxOk(IMPORT), 'start.import.js 语法错误');
});

test('WB-028 引擎菜单 ARIA：role=menu 与触发器 aria-controls 配对', () => {
  // 菜单项为 menuitemradio（renderEngineMenu 动态构建）——容器必须声明
  // role=menu 才构成完整 menu/menuitemradio ARIA 模式
  assert.match(HTML, /id="engineMenu"[^>]*role="menu"/, 'engineMenu 必须声明 role=menu');
  assert.match(HTML, /aria-haspopup="menu"[^>]*aria-controls="engineMenu"/,
    'enginePill 必须以 aria-controls 指向菜单容器');
});

test('WB-029 键盘焦点可见性：:focus-visible 规则必须存在', () => {
  assert.match(CSS, /:focus-visible/, 'start.css 必须有键盘焦点样式（此前全文件 0 处 focus）');
});

test('WB-027 导入向导焦点管理：初始聚焦 + Tab 陷阱 + 关闭归还', () => {
  assert.match(IMPORT, /closeBtn\.focus\(\)/, '打开向导必须把初始焦点移入弹层');
  assert.match(IMPORT, /modal\.addEventListener\('keydown'/, '弹层必须接管按键');
  assert.match(IMPORT, /'Tab'/, '必须处理 Tab（焦点陷阱）');
  assert.match(IMPORT, /lastFocus/, '必须记录触发元素');
  assert.match(IMPORT, /lastFocus\.focus\(\)/, '关闭必须归还焦点');
});

// WB-114（2026-09-26 审计）：归档 pywebview 栈的 win 桥分支已删——
// 适配层不得再出现 pywebview/win 端引用（纯死代码面回归锁）。
// 断言剥掉注释只看代码（注释中的历史提及不算回归）。
test('WB-114 Host 适配层收敛双端：win 归档桥分支不得回归', () => {
  const code = HOSTJS.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.ok(!/pywebview/.test(code), 'start.js 代码不得再引用 pywebview 归档桥');
  assert.ok(!/winApi/.test(code), 'start.js 代码不得残留 winApi 桥');
  assert.ok(!/\? 'win'/.test(code) && !/=== 'win'/.test(code),
    "start.js 代码不得再出现 'win' 端判定");
  assert.match(code, /kind: function \(\) \{ return andApi\(\) \? 'android' : \(csApi\(\) \? 'cs' : null\); \}/,
    'kind() 必须收敛 android/cs 双端判定');
});

// WB-125（2026-09-26 审计）：四个脚本的加载顺序是硬契约——任何重排即
// ReferenceError 白屏（start.main.js 依赖前三个文件的全局；本断言按序
// 提取 script src 锁定顺序）
test('WB-125 脚本加载顺序硬契约：Host → snake → import → main', () => {
  const srcs = [...HTML.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);
  assert.deepEqual(srcs, ['start.js', 'start.snake.js', 'start.import.js', 'start.main.js'],
    '脚本加载顺序不得重排（重排即白屏）');
});

// WB-126（2026-09-26 审计）：导入弹层初始隐藏依赖 hidden 属性与高特异度
// CSS 规则配对——此前零回归测试，拆掉任一半即静默失效
test('WB-126 导入弹层初始隐藏：hidden 属性 + [hidden] CSS 规则双断言', () => {
  assert.match(HTML, /id="importModal"[^>]*\shidden>/,
    '标记层必须带 hidden 属性（初始隐藏语义）');
  assert.match(CSS, /#importModal\[hidden\]\s*\{\s*display:\s*none;\s*\}/,
    '作者 display:flex 会压过 hidden 的 UA 规则——[hidden] 高特异度配对规则必须存在');
});

// WB-105（2026-09-26 审计）：meta CSP 不得再含 frame-ancestors——规范明文
// 该指令在 meta 中被忽略，保留即「安全声明失真」
test('WB-105 meta CSP 无效指令：frame-ancestors/report-uri 不得回归', () => {
  const csp = HTML.match(/http-equiv="Content-Security-Policy"\s*\n?\s*content="([^"]*)"/);
  assert.ok(csp, 'CSP meta 必须存在');
  assert.ok(!/frame-ancestors/.test(csp[1]), 'meta CSP 不得含 frame-ancestors（meta 中被忽略）');
  assert.ok(!/report-uri/.test(csp[1]), 'meta CSP 不得含 report-uri（meta 中被忽略）');
});

// WB-131（2026-09-26 审计）：无 icon 声明时每开新标签产生 favicon 404 请求
test('WB-131 favicon：data: URI icon 声明必须存在', () => {
  assert.match(HTML, /<link rel="icon" href="data:image\/svg\+xml,/, '必须以 data: URI 声明 icon');
});

// WB-113（2026-09-26 审计）：向导步骤变化读屏可感知
test('WB-113 导入向导步骤区 aria-live：role=status + polite', () => {
  assert.match(HTML, /id="imBody"[^>]*role="status"[^>]*aria-live="polite"/,
    'imBody 必须声明 role=status aria-live=polite');
});

// WB-112（2026-09-26 审计）：贪吃蛇全屏浮层 dialog 语义与焦点管理（对齐
// 导入向导模式）
test('WB-112 贪吃蛇浮层：role=dialog/aria-modal + 焦点管理 + Tab 陷阱', () => {
  assert.match(HTML, /id="snakeOverlay"[^>]*role="dialog"[^>]*aria-modal="true"/,
    '浮层必须声明 role=dialog aria-modal=true');
  assert.match(SNAKE, /lastFocus = document\.activeElement/, '打开前必须记录触发元素');
  assert.match(SNAKE, /closeBtn && typeof closeBtn\.focus === 'function'[\s\S]{0,60}closeBtn\.focus\(\)/,
    '打开必须把初始焦点移入浮层（关闭钮）');
  assert.match(SNAKE, /lastFocus && typeof lastFocus\.focus === 'function'[\s\S]{0,60}lastFocus\.focus\(\)/,
    '关闭必须归还焦点');
  assert.match(SNAKE, /ov\.addEventListener\('keydown'[\s\S]{0,200}e\.key !== 'Tab'/,
    '浮层必须接管 Tab（焦点陷阱）');
});

// WB-110（2026-09-26 审计）：吃食分支 updScore(true)——.pop 动画触发条件
test('WB-110 加分视觉反馈：step 吃食分支必须 updScore(true)', () => {
  assert.match(SNAKE, /if \(grew\) updScore\(true\);/, '吃食加分必须触发 .pop 缩放动画');
  assert.ok(!/updScore\(false\)[\s\S]{0,80}\/\/ 分数变化时才刷新/.test(SNAKE),
    '旧的恒 false 调用不得回归');
});

// WB-111（2026-09-26 审计）：prefers-reduced-motion 双侧关闭（CSS 动画 +
// canvas 屏震/红闪）
test('WB-111 减动效偏好：CSS 媒体查询 + canvas shake/flash 渲染门控', () => {
  assert.match(CSS, /@media \(prefers-reduced-motion: reduce\)/, 'start.css 必须有减动效媒体查询');
  assert.match(SNAKE, /prefers-reduced-motion/, 'start.snake.js 必须探测减动效偏好');
  assert.match(SNAKE, /!reduceMotion && shake > 0/, '屏震必须被 reduceMotion 门控');
  assert.match(SNAKE, /!reduceMotion && flash > 0/, '死亡红闪必须被 reduceMotion 门控');
});

// WB-109（2026-09-26 审计）：主搜索框不得成为零焦点指示控件
//（断言剥掉 CSS 注释——注释中的历史描述不算回归）
test('WB-109 搜索框焦点指示：outline:none 规则不得回归', () => {
  const cssCode = CSS.replace(/\/\*[\s\S]*?\*\//g, '');
  assert.ok(!/\.search input:focus-visible\s*\{[^}]*outline:\s*none/.test(cssCode),
    '.search input:focus-visible outline:none 不得回归');
  assert.match(cssCode, /\.search:focus-within/, '胶囊容器必须有 focus-within 组级描边');
});

// WB-132（2026-09-26 审计）：壁纸控件面向用户显示中文名
test('WB-132 壁纸 tooltip：WALLPAPERS 表必须有中文 label 字段', () => {
  assert.match(MAINJS, /label:'暖洋红'/, 'magenta 必须有中文名');
  assert.match(MAINJS, /label:'晨曦青'/, 'lime 必须有中文名');
  assert.match(MAINJS, /label:'暮蓝'/, 'twilight 必须有中文名');
  assert.match(MAINJS, /label:'星紫'/, 'violet 必须有中文名');
  assert.match(MAINJS, /d\.title = WALLPAPERS\[idx\]\.label;/, 'tooltip 必须用 label');
  assert.ok(!/d\.title = WALLPAPERS\[idx\]\.name;/.test(MAINJS), 'tooltip 不得回退到内部文件名');
});

// WB-108（2026-09-26 审计）：引擎菜单两条关闭路径都必须复位 aria-expanded
test('WB-108 引擎菜单关闭路径：aria-expanded 双路径复位', () => {
  const resets = [...MAINJS.matchAll(/setAttribute\('aria-expanded', 'false'\)/g)].length;
  assert.ok(resets >= 3,
    'aria-expanded=false 复位须覆盖 toggleEngineMenu/selectEngine/document 点击三条路径');
});

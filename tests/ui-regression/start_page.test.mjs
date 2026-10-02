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
  // 去宿主对象引用后应可解析（宿主对象运行时由两端注入）。
  // SP-135（审计 2026-09-23 清单·SP1 批）：C# 单轨后 chrome.webview 是正典
  // 宿主引用——语法消毒面必须覆盖三宿主（pywebview 归档/AegisBridge/chrome.webview）。
  new Function(body.replace(/window\.pywebview/g, 'window.__h1__')
                   .replace(/window\.AegisBridge/g, 'window.__h2__')
                   .replace(/chrome\.webview/g, 'window.__h3__'));
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

// SP-043（审计 2026-09-23 清单·SP1 批）：BUG-013 此前零静态回归——targetSdk 36
// 起返回事件经 OnBackInvokedCallback 分发（手势导航 onKeyDown(KEYCODE_BACK)
// 永远收不到，返回直接退出应用）。Manifest 声明 + OnBackPressedCallback 接管
// 双断言锁定，拆掉任一半即回归。
test('BUG-013 返回接管：Manifest 预测性返回声明 + OnBackPressedCallback 接管', () => {
  const manifest = readFileSync(join(ROOT, 'android', 'app', 'src', 'main', 'AndroidManifest.xml'), 'utf8');
  assert.match(manifest, /android:enableOnBackInvokedCallback="true"/,
    'Manifest 必须启用 OnBackInvokedCallback 返回分发（targetSdk 36 手势导航语义）');
  const mainKt = readFileSync(join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'MainActivity.kt'), 'utf8');
  assert.match(mainKt, /import androidx\.activity\.OnBackPressedCallback/,
    '必须引入 OnBackPressedCallback（返回接管的唯一正典路径）');
  assert.match(mainKt, /class BackPressHandler\s*:\s*OnBackPressedCallback/,
    'BackPressHandler 必须继承 OnBackPressedCallback（手势/按键双路径统一接管）');
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
  // SP-042（审计 2026-09-23 清单·SP1 批）：C# 单轨正典打包链——csproj 才是
  // 现役打包事实来源（上一行 legacy spec 仅归档守护）；SP-145 后画板资源
  // 暂存已迁 dist/geogebra-cache/，csproj 条件打包断言必须同步锁定
  const csproj = readFileSync(join(ROOT, 'windows', 'src', 'Aegis.Windows.App', 'Aegis.Windows.App.csproj'), 'utf8');
  assert.match(csproj, /dist\\geogebra-cache/, 'C# csproj 必须从 dist/geogebra-cache 条件打包画板资源（单轨事实来源）');
  assert.match(csproj, /GeoGebra\.html/, 'C# csproj 必须以 GeoGebra.html 入口存在为打包条件（fail-closed）');
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

// ═══ WB-031..100 W5 批（审计 2026-09-23 清单）补充断言 ═══

// WB-043（审计 2026-09-23 清单·W5 批）：background-image 不可插值——无效
// transition 不得回归（如需过渡须双层蒙版交叉淡入方案；剥注释只看代码）
test('WB-043 壁纸层无效过渡：background-image transition 不得回归', () => {
  const cssCode = CSS.replace(/\/\*[\s\S]*?\*\//g, '');
  assert.ok(!/transition\s*:[^;}]*background-image/.test(cssCode),
    'background-image 不可插值动画——transition 声明无效且具误导性');
});

// WB-046（审计 2026-09-23 清单·W5 批）：音效开关切换态读屏可感知
test('WB-046 音效开关 aria-pressed：标记声明 + JS 打开/切换双点同步', () => {
  assert.match(HTML, /id="snakeSound"[^>]*aria-pressed="false"/,
    '音效开关必须声明 aria-pressed 初始态');
  assert.match(SNAKE, /setAttribute\('aria-pressed', muted \? 'true' : 'false'\)/g,
    'JS 必须在静音态变化时同步 aria-pressed');
  const syncs = [...SNAKE.matchAll(/setAttribute\('aria-pressed'/g)].length;
  assert.ok(syncs >= 2, '打开复位与点击切换两个路径都必须同步');
});

// WB-049（审计 2026-09-23 清单·W5 批）：页脚提示与实际行为一致——
// Ctrl+L 聚焦的是本页搜索框（地址栏属浏览器 chrome，不在 NTP）
test('WB-049 页脚提示文案：Ctrl+L 指向搜索框而非不存在的地址栏', () => {
  assert.match(HTML, /Ctrl\+L 聚焦搜索框/, '文案必须对齐实际行为');
  assert.ok(!/Ctrl\+L 聚焦地址栏/.test(HTML), '「聚焦地址栏」旧文案不得回归');
  assert.match(MAINJS, /e\.key\.toLowerCase\(\) === 'l'/, 'Ctrl+L 行为保持存在');
});

// WB-050（审计 2026-09-23 清单·W5 批）：autofocus 触屏弹软键盘——
// 标记层移除 autofocus，改由 JS 按 pointer:fine 条件聚焦
test('WB-050 autofocus 条件化：标记层无 autofocus，JS 按 pointer:fine 聚焦', () => {
  assert.ok(!/\sautofocus/.test(HTML), '标记层不得保留 autofocus（触屏加载即弹软键盘）');
  assert.match(MAINJS, /matchMedia\('\(pointer: fine\)'\)/,
    '必须按精指针媒体条件聚焦');
  assert.match(MAINJS, /focusSearchOnFinePointer|getElementById\('q'\)[\s\S]{0,40}focus\(\)/,
    '聚焦目标必须是搜索框');
});

// WB-098（审计 2026-09-23 清单·W5 批）：默认壁纸三处硬编码一致性——
// start.css / start.main.js / C# NtpAssets / Android AegisHomeBridge 单值
test('WB-098 默认壁纸跨端一致：aurora-twilight.jpg 四处名单单值', () => {
  const DEFAULT = 'aurora-twilight.jpg';
  assert.match(CSS, new RegExp(`wallpapers/${DEFAULT}`),
    'start.css 初始背景必须用默认壁纸');
  assert.match(MAINJS, new RegExp(`current = '${DEFAULT}'`),
    'start.main.js current 初始值必须与 CSS 一致');
  const cs = readFileSync(join(ROOT, 'windows', 'src', 'Aegis.Windows.App', 'Chrome', 'Ntp', 'NtpAssets.cs'), 'utf8');
  assert.match(cs, new RegExp(`DefaultWallpaper = "${DEFAULT}"`),
    'C# NtpAssets.DefaultWallpaper 必须一致');
  const kt = readFileSync(join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'aegis', 'browser', 'AegisHomeBridge.kt'), 'utf8');
  assert.ok(kt.includes(`"${DEFAULT}"`), 'Android AegisHomeBridge 默认壁纸必须一致');
});

// WB-100（审计 2026-09-23 清单·W5 批）：得分变化读屏可感知
test('WB-100 得分 chip aria-live：polite 播报且仅作用于得分', () => {
  assert.match(HTML, /class="chip" aria-live="polite"><span class="k">得分</,
    '得分 chip 必须声明 aria-live=polite');
  const bestChip = HTML.match(/class="chip best"([^>]*)>/);
  assert.ok(bestChip && !/aria-live/.test(bestChip[1]),
    '「最高」chip 静态不播报（避免重复播报）');
});

// ═══ 2026-10-01 审计（第三轮 241 项）补充断言 ═══

// WB-133：贪吃蛇键盘守卫——模块级 isOpen 标志（行为级回归在
// shared/shell/snake.test.js 以干净实例驱动；此处锁代码结构不回退）
test('WB-133 贪吃蛇输入守卫：模块级 isOpen，不得回退内联 display 判定', () => {
  assert.match(SNAKE, /var isOpen = false;/, '必须声明模块级 isOpen 标志');
  assert.match(SNAKE, /isOpen = true;\s*\/\/ WB-133|isOpen = true;\s*$/,
    'open() 必须置位 isOpen');
  assert.match(SNAKE, /isOpen = false;\s*\/\/ WB-133|isOpen = false;\s*$/,
    'close() 必须复位 isOpen');
  const guardBody = SNAKE.substring(SNAKE.indexOf("document.addEventListener('keydown'"));
  assert.match(guardBody, /if \(!isOpen\) return;/,
    '键盘守卫必须以 isOpen 短路（浮层初始由 CSS 类隐藏——内联 display 为空串，display 判定在首开前放行 Escape 清零最高分）');
  // 断言剥掉注释——守卫注记中的历史表述不算回归
  const snakeCode = SNAKE.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.ok(!/ov\.style\.display === 'none'/.test(snakeCode),
    '旧「内联 display === none」守卫不得回归（键盘/触摸两处）');
});

// WB-137：restoreBox 显示必须移除 hidden 属性配对（不压 style.display）
test('WB-137 restoreBox hidden 配对：removeAttribute 配对，不得 style.display 压制', () => {
  assert.match(MAINJS, /removeAttribute\('hidden'\)/,
    '显示必须移除 hidden 属性（行为级回归在 start_main.test.mjs WB-129/137）');
  assert.ok(!/restoreBox[^;]*\.style\.display|box\.style\.display = 'block'/.test(MAINJS),
    '不得以 style.display 压过 hidden 属性（语义残留）');
});

// WB-140：error/unhandledrejection 监听必须在首文件 start.js 注册
test('WB-140 全局错误监听前移：start.js 注册，start.main.js 不得残留', () => {
  assert.match(HOSTJS, /window\.addEventListener\('error'/, 'start.js 必须注册 error 监听');
  assert.match(HOSTJS, /window\.addEventListener\('unhandledrejection'/,
    'start.js 必须注册 unhandledrejection 监听');
  const mainCode = MAINJS.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.ok(!/window\.addEventListener\('error'/.test(mainCode),
    'start.main.js 不得重复注册（最末脚本注册时前三文件顶层异常已零上报）');
  assert.ok(!/window\.addEventListener\('unhandledrejection'/.test(mainCode),
    'start.main.js 不得残留 unhandledrejection 注册');
});

// WB-141：forced-colors 高对比模式规则
test('WB-141 forced-colors 规则：高对比模式必须恢复系统配色', () => {
  assert.match(CSS, /@media \(forced-colors: active\)/,
    'start.css 必须有 forced-colors 媒体查询（此前全文件 0 处）');
  const fcBlock = CSS.substring(CSS.indexOf('@media (forced-colors: active)'));
  for (const sysColor of ['CanvasText', 'ButtonFace', 'ButtonText']) {
    assert.ok(fcBlock.includes(sysColor), `高对比规则必须使用系统色 ${sysColor}`);
  }
});

// WB-142：coarse pointer 触控目标补齐（.link-btn/.snake-sound/.snake-close ≥44px）
test('WB-142 触控目标保底补齐：三个遗漏控件进入 coarse pointer 规则', () => {
  const start = CSS.indexOf('@media (pointer: coarse)');
  assert.ok(start > 0, 'coarse pointer 媒体查询必须存在');
  // 媒体块整体范围：截到下一个 @media（或文末）——首条规则内的 } 不是块边界
  const next = CSS.indexOf('@media', start + 10);
  const coarse = CSS.substring(start, next === -1 ? CSS.length : next);
  for (const sel of ['.link-btn', '.snake-sound', '.snake-close']) {
    assert.ok(coarse.includes(sel), `${sel} 必须纳入触控目标保底（此前 <44px）`);
  }
  assert.match(coarse, /min-height:44px/, '保底尺寸必须达到 44px');
});

// WB-143：placeholder 对比度 ≥4.5:1（#9aa1ad 实测 2.9:1 不得回归）
test('WB-143 placeholder 对比度：不得回归低对比灰', () => {
  const cssCode = CSS.replace(/\/\*[\s\S]*?\*\//g, '');
  assert.ok(!/placeholder\s*\{\s*color:\s*#9aa1ad/.test(cssCode),
    '#9aa1ad（白底 2.9:1 < AA）不得回归');
  assert.match(cssCode, /\.search input::placeholder\s*\{\s*color:\s*#6e747f;\s*\}/,
    'placeholder 必须用加深灰 #6e747f（白底 4.70:1）');
});

// WB-144：移动端输入框字号 ≥16px（防 iOS 聚焦自动放大跳变）
test('WB-144 移动端输入字号：≤640px 断点不得低于 16px', () => {
  const mobile = CSS.substring(CSS.indexOf('@media (max-width: 640px)'));
  const inputRule = mobile.match(/\.search input\s*\{[^}]*font-size:\s*(\d+)px[^}]*\}/);
  assert.ok(inputRule, '移动端断点必须有 .search input 字号规则');
  assert.ok(parseInt(inputRule[1], 10) >= 16,
    `移动端输入字号必须 ≥16px（实际 ${inputRule[1]}px——<16px 触发 iOS 聚焦整页放大）`);
});

// WB-149：CSP img-src 必须放行 data:（WB-131 favicon data: URI 依赖）
test('WB-149 CSP img-src data: 许可必须锁定（favicon data: URI 依赖）', () => {
  const csp = HTML.match(/http-equiv="Content-Security-Policy"\s*\n?\s*content="([^"]*)"/);
  assert.ok(csp, 'CSP meta 必须存在');
  assert.match(csp[1], /img-src 'self' file: data:/,
    "img-src 必须含 data:（去掉即 favicon 404 回归——WB-131）");
});

// WB-151：__test 钩子条件注入——生产脚本不得无条件挂载受控写入面
test('WB-151 __test 条件注入：测试标志门控 + 冻结，生产零暴露', () => {
  assert.match(SNAKE, /__AEGIS_SNAKE_TEST__/,
    '__test 挂载必须由 window.__AEGIS_SNAKE_TEST__ 测试标志门控');
  assert.match(SNAKE, /__test: TEST_HOOKS \? \{/, '钩子对象必须条件挂载');
  assert.match(SNAKE, /Object\.freeze\(api\.__test\)/, '测试态钩子面必须冻结');
  const bare = SNAKE.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.ok(!/return \{\s*open: open, close: close,\s*__test: \{/.test(bare),
    '不得回退为无条件内联 __test 对象（行为级回归在 snake.test.js）');
});

// 贪吃蛇游戏逻辑回归测试（Node.js 无头运行——Mock DOM 后加载 start.snake.js）
// 每次修改 start.snake.js 后必须运行此文件：node shared/shell/snake.test.js
"use strict";

const assert = require("assert");
const path = require("path");
const fs = require("fs");

// ═══ Mock DOM 环境 ═══
// WB-081（审计 2026-09-23 清单·W5 批）：全部 mock 2D 上下文共享 fillRect
// 记录器——drawPixelText/DIG 位图覆盖测试按增量计数断言绘制行为
const fillCalls = [];
function createMockContext2D() {
  return {
    fillRect: (...args) => { fillCalls.push(args); }, clearRect: () => {},
    beginPath: () => {}, moveTo: () => {}, lineTo: () => {}, stroke: () => {},
    arc: () => {}, fill: () => {}, closePath: () => {},
    save: () => {}, restore: () => {}, translate: () => {},
    createLinearGradient: () => ({ addColorStop: () => {} }),
    setImageSmoothingEnabled: () => {},
    drawImage: () => {},
    fillText: () => {},
    imageSmoothingEnabled: true,
    fillStyle: "", strokeStyle: "", lineWidth: 1,
    lineJoin: "", lineCap: "", globalAlpha: 1,
    shadowColor: "", shadowBlur: 0,
  };
}

function createMockCanvas() {
  const el = {
    width: 480, height: 480,
    style: { width: "", height: "" },
    clientWidth: 480,
    parentElement: { clientWidth: 480 },
    getContext: () => createMockContext2D(),
    addEventListener: () => {},
    addHandler: () => {},
  };
  return el;
}

const elements = {};
function mockEl(id, overrides) {
  if (!elements[id]) {
    elements[id] = Object.assign({
      textContent: "", innerText: "",
      style: { display: "", width: "", height: "" },
      classList: { add: () => {}, remove: () => {} },
      addEventListener: () => {},
      // WB-046（审计 2026-09-23 清单·W5 批）：mock 补 setAttribute 记录——
      // 音效开关 aria-pressed 同步断言需要读取属性写入
      _attrs: {},
      setAttribute(n, v) { this._attrs[n] = String(v); },
      getAttribute(n) { return n in this._attrs ? this._attrs[n] : null; },
      focus: () => {}, selectAll: () => {},
      offsetWidth: 0,
      isSelected: false,
      Items: { Count: 0, Clear: () => {} },
      ItemsSource: null,
      ItemTemplateSelector: null,
      SelectedItem: null,
      SelectedIndex: -1,
      Tag: null,
      Value: null,
      IsOpen: false,
      CaretIndex: 0,
      Text: "",
    }, overrides || {});
  }
  return elements[id];
}

const mockDocument = {
  getElementById: (id) => mockEl(id),
  // WB-133（2026-10-01 审计）：捕获 document 级监听器——键盘守卫回归
  // 需要真实驱动 start.snake.js 注册的 keydown 处理器（此前桩为 no-op）
  _listeners: {},
  addEventListener: (type, fn) => {
    (mockDocument._listeners[type] = mockDocument._listeners[type] || []).push(fn);
  },
  createElement: (tag) => {
    if (tag === "canvas") return createMockCanvas();
    return { style: {}, appendChild: () => {}, addEventListener: () => {} };
  },
  body: { innerText: "mock page content" },
};

const mockStorage = {};
const mockGlobal = {
  document: mockDocument,
  window: {
    devicePixelRatio: 1,
    AudioContext: undefined,
    webkitAudioContext: undefined,
    addEventListener: () => {},
  },
  localStorage: {
    getItem: (k) => mockStorage[k] || null,
    setItem: (k, v) => { mockStorage[k] = v; },
  },
  requestAnimationFrame: (cb) => { return 1; },  // 不真正循环
  cancelAnimationFrame: () => {},
  setInterval: () => 1,
  clearInterval: () => {},
  setTimeout: (cb) => { return 1; },
  performance: { now: () => Date.now() },
  Math: Math,
  console: console,
};

// ═══ 加载贪吃蛇模块 ═══
const vm = require("vm");
const code = fs.readFileSync(
  path.join(__dirname, "start.snake.js"), "utf8");

// 建立 DOM mock 上下文
mockEl("snakeOverlay");
mockEl("snakeCanvas");
mockEl("snakeScore");
mockEl("snakeBest");
mockEl("snakeSound");
mockEl("snakeVeil");
mockEl("veilEmoji");
mockEl("veilTitle");
mockEl("veilSub");
mockEl("veilBtn");
mockEl("snakeClose");

// WB-151（2026-10-01 审计）：__test 钩子改条件注入——生产脚本不再随成品
// 挂载受控写入面；无头回归在加载前显式声明测试标志
mockGlobal.window.__AEGIS_SNAKE_TEST__ = true;

const sandbox = Object.assign({}, mockGlobal, {
  document: mockDocument,
  window: mockGlobal.window,
  localStorage: mockGlobal.localStorage,
  requestAnimationFrame: mockGlobal.requestAnimationFrame,
  cancelAnimationFrame: mockGlobal.cancelAnimationFrame,
});
sandbox.globalThis = sandbox;

// 注入 canvas mock
elements["snakeCanvas"] = createMockCanvas();
mockDocument.getElementById = (id) => {
  if (id === "snakeCanvas") return elements["snakeCanvas"];
  return mockEl(id);
};

const context = vm.createContext(sandbox);
vm.runInContext(code, context, { filename: "start.snake.js" });

const Snake = sandbox.Snake;
const openSnake = sandbox.openSnake;

// ═══ 测试 ═══
let passed = 0, failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ✅ ${name}`);
  } catch (e) {
    failed++;
    console.error(`  ❌ ${name}\n     ${e.message}`);
  }
}

console.log("\n=== 贪吃蛇回归测试 ===\n");

test("模块导出 open/close", () => {
  assert.ok(Snake, "Snake 模块存在");
  assert.strictEqual(typeof Snake.open, "function", "open 是函数");
  assert.strictEqual(typeof Snake.close, "function", "close 是函数");
});

test("open() 初始化不崩溃", () => {
  Snake.open();
});

test("close() 不崩溃", () => {
  Snake.close();
});

test("open → close → open 生命周期安全", () => {
  Snake.open();
  Snake.close();
  Snake.open();  // 再次打开不崩
  Snake.close();
});

test("open 后元素可见", () => {
  Snake.open();
  assert.strictEqual(elements["snakeOverlay"].style.display, "flex");
});

test("close 后元素隐藏", () => {
  Snake.close();
  assert.strictEqual(elements["snakeOverlay"].style.display, "none");
  Snake.open();  // 恢复
});

test("初始得分为 0", () => {
  Snake.open();
  assert.strictEqual(elements["snakeScore"].textContent, "0");
});

test("最高分初始加载", () => {
  mockStorage["snakeBest"] = "42";
  Snake.open();
  // loadBest 在 open 中调用
  mockStorage["snakeBest"] = null;  // 清理
  Snake.open();
});

test("连续 open/close 10 次不崩溃（生命周期压力）", () => {
  for (let i = 0; i < 10; i++) {
    Snake.open();
    Snake.close();
  }
  Snake.open();  // 确保最终状态可用
});

test("共享 JS 语法: 无 dt 泄漏到 render 闭包外", () => {
  // 确保 render 函数不引用 loop 内的局部变量
  const code_snippet = code;
  // render 函数体内不应引用 loop 的局部 dt（已修复为参数传入）
  const renderIdx = code_snippet.indexOf("function render(");
  assert.ok(renderIdx > 0, "render 函数存在");
  const renderBody = code_snippet.substring(
    code_snippet.indexOf("{", renderIdx),
    code_snippet.indexOf("}", code_snippet.indexOf("drawPixelText", renderIdx))
  );
  // 修复后 render(dt) 接收 dt 参数——不再引用 loop 局部变量
  assert.ok(
    code_snippet.includes("function render(dt)"),
    "render 函数应接收 dt 参数"
  );
});

// ═══ WB-016..019：核心逻辑行为级测试（经 Snake.__test 钩子——
// 钩子只读状态 + 受控写入，不改变运行时行为） ═══
const T = Snake.__test;

test("__test 钩子完整", () => {
  assert.ok(T, "__test 钩子存在");
  ["turn", "step", "freeCell", "state", "score", "body", "dir", "queue",
   "food", "bonus", "setFood", "setBonus",
   // WB-076..081（审计 2026-09-23 清单·W5 批）：新增只读/受控钩子
   "stepMs", "particles", "best", "primaryAction", "drawPixelText"].forEach((k) =>
    assert.ok(T[k] !== undefined, "钩子缺少 " + k));
});

test("WB-016 turn() 拒绝反向与同向", () => {
  Snake.open();
  assert.strictEqual(T.queue().length, 0, "初始队列为空");
  T.turn(-1, 0);  // dir={1,0}（向右）→ 反向
  assert.strictEqual(T.queue().length, 0, "反向入队被拒绝");
  T.turn(1, 0);   // 同向
  assert.strictEqual(T.queue().length, 0, "同向入队被拒绝");
  T.turn(0, -1);  // 垂直 → 接受
  assert.strictEqual(T.queue().length, 1, "垂直转向入队");
  Snake.close();
});

test("WB-016 turn() 队列上限 3", () => {
  Snake.open();
  T.turn(0, -1);  // up
  T.turn(-1, 0);  // left（相对 up 合法）
  T.turn(0, 1);   // down（相对 left 合法）
  assert.strictEqual(T.queue().length, 3);
  T.turn(1, 0);   // 第 4 个 → 丢弃
  assert.strictEqual(T.queue().length, 3, "超限输入被丢弃");
  Snake.close();
});

test("WB-017 freeCell() 不落在任何占用格", () => {
  Snake.open();
  const body = T.body();
  for (let i = 0; i < 200; i++) {
    const c = T.freeCell();
    assert.ok(c, "棋盘未满时必须返回空格");
    assert.ok(!body.some((s) => s.x === c.x && s.y === c.y), "不得落在蛇身");
    const f = T.food();
    assert.ok(!(c.x === f.x && c.y === f.y), "不得落在食物");
    const bo = T.bonus();
    if (bo) assert.ok(!(c.x === bo.x && c.y === bo.y), "不得落在奖励果");
  }
  Snake.close();
});

test("WB-018 step() 撞墙死亡且蛇头不出界", () => {
  Snake.open();
  T.setFood(2, 12);  // 食物放路径后方——不会误吃
  // open() 后 state='start'——step() 无状态门禁（loop 才检查），直接驱动
  let guard = 0;
  while (T.state() !== "dead" && guard++ < 30) T.step();
  assert.strictEqual(T.state(), "dead", "撞右墙后死亡");
  assert.ok(T.body()[0].x < 24, "死亡后蛇头不出界");
  Snake.close();
});

test("WB-018 step() 撞自身死亡", () => {
  Snake.open();
  T.setFood(20, 20);
  // 构造 U 形蛇：头 (5,5) 向右 → 前方 (6,5) 是自身第 4 节
  const b = T.body();
  b.length = 0;
  b.push({ x: 5, y: 5 }, { x: 5, y: 6 }, { x: 6, y: 6 }, { x: 6, y: 5 }, { x: 7, y: 5 });
  T.step();
  assert.strictEqual(T.state(), "dead", "头撞自身第 4 节后死亡");
  assert.strictEqual(T.body()[0].x, 5, "死亡步不前移");
  Snake.close();
});

test("WB-019 吃食 +10 且蛇身增长", () => {
  Snake.open();
  const b = T.body();  // (7,12),(6,12),(5,12) 向右
  T.setFood(8, 12);    // 头前方一格
  const before = b.length;
  T.step();
  assert.strictEqual(T.score(), 10, "吃食 +10");
  assert.strictEqual(b.length, before + 1, "吃食后蛇身 +1");
  const f = T.food();
  assert.ok(!(f.x === 8 && f.y === 12), "食物被吃后重新放置");
  Snake.close();
});

test("WB-019 吃奖励 +50 且奖励消失", () => {
  Snake.open();
  T.setFood(20, 20);
  T.setBonus(8, 12);  // 头前方一格放奖励果
  T.step();
  assert.strictEqual(T.score(), 50, "奖励 +50");
  assert.strictEqual(T.bonus(), null, "奖励被吃后消失");
  Snake.close();
});

test("WB-019 奖果 TTL 耗尽自动消失（中心绕圈 40 步不死）", () => {
  Snake.open();
  T.setFood(20, 20);
  T.setBonus(9, 9);   // 远离路径
  // 5×5 方形绕圈：右5 上5 左5 下5 …… 8 腿 = 40 步；区域 x:7..12 y:7..12，
  // 蛇长 3 无自撞，不触墙（open() 后 state='start'——step 无状态门禁）
  const legs = [[0, -1], [-1, 0], [0, 1], [1, 0]];
  for (let leg = 0; leg < 8 && T.bonus(); leg++) {
    T.turn(legs[leg % 4][0], legs[leg % 4][1]);
    for (let s = 0; s < 5 && T.bonus(); s++) T.step();
  }
  assert.notStrictEqual(T.state(), "dead", "40 步绕圈期间存活");
  assert.strictEqual(T.bonus(), null, "TTL 耗尽奖励消失");
  assert.strictEqual(T.score(), 0, "绕圈未吃食");
  Snake.close();
});

// ═══ WB-076..081（审计 2026-09-23 清单·W5 批）：提速下限/最高分即时更新/
// localStorage 往返/四态文案/die 粒子/DIG 位图覆盖——此前零测试面 ═══

test("WB-076 提速曲线下限：连续吃食 stepMs 单调下降并在 ~70 处触底稳定", () => {
  Snake.open();
  assert.strictEqual(T.stepMs(), 150, "初始步进间隔 150ms");
  // 触底需 ~27 次吃食（蛇长随之 +27）——直线吃必撞墙，改走简单蛇形路径
  //（各步互不重复、不出界），食物每步放在头前方一格 → 每步都吃
  const legs = [
    [1, 0, 13],   // → x:7..20（y=12）
    [0, 1, 1],
    [-1, 0, 15],  // ← x:20..5（y=13）
    [0, 1, 1],
    [1, 0, 15],   // → （y=14）
    [0, 1, 1],
    [-1, 0, 15],  // ← （y=15）
  ];
  outer:
  for (const [dx, dy, n] of legs) {
    T.turn(dx, dy);
    for (let s = 0; s < n; s++) {
      const head = T.body()[0];
      T.setFood(head.x + dx, head.y + dy);   // 路径正前方
      T.step();
      if (T.state() === "dead") break outer;
      if (T.stepMs() <= 70) break outer;     // 触底即止
    }
  }
  // open() 后 state='start'（step 无状态门禁——对齐 WB-018/019 驱动方式）
  assert.notStrictEqual(T.state(), "dead", "蛇形路径上吃食不应死亡");
  // 下限性质：stepMs > 70 才再降 3ms——触底值必然 ≤70 且 > 60
  //（计划口径「提速曲线下限 70」）
  assert.ok(T.stepMs() <= 70 && T.stepMs() > 60, `触底值落在下限区（实际 ${T.stepMs()}）`);
  const floor = T.stepMs();
  const head = T.body()[0];
  T.setFood(head.x + 1, head.y);
  T.step();
  assert.strictEqual(T.stepMs(), floor, "触底后继续吃食不再提速");
  Snake.close();
});

test("WB-077 最高分即时更新：吃食后内存与 UI 同步，localStorage 延迟持久化", () => {
  delete mockStorage["snakeBest"];
  Snake.open();
  assert.strictEqual(T.best(), 0, "初始内存最高分 0");
  const head = T.body()[0];
  T.setFood(head.x + 1, head.y);
  T.step();
  assert.strictEqual(T.score(), 10, "吃食 +10");
  assert.strictEqual(T.best(), 10, "最高分内存即时更新（updScore 内随分数提升）");
  assert.strictEqual(elements["snakeBest"].textContent, "10", "最高分 chip 同步刷新");
  assert.strictEqual(mockStorage["snakeBest"], undefined,
    "localStorage 不在吃食路径写盘（写放大治理——持久化集中在 persistBest）");
  Snake.close();
  assert.strictEqual(mockStorage["snakeBest"], "10", "close() 触发 persistBest 落盘");
});

test("WB-078 localStorage 往返：落盘 → 重开加载 → 死亡再落盘", () => {
  delete mockStorage["snakeBest"];
  mockStorage["snakeBest"] = "7";
  Snake.open();
  assert.strictEqual(T.best(), 7, "重开必须从 localStorage 加载既有最高分");
  assert.strictEqual(elements["snakeBest"].textContent, "7");
  const head = T.body()[0];
  T.setFood(head.x + 1, head.y);
  T.step();                                        // 吃到 10 分 → best 即时 10
  T.setFood(20, 2);                                // 食物移开——撞墙死
  let g = 0;
  while (T.state() !== "dead" && g++ < 30) T.step();
  assert.strictEqual(T.state(), "dead");
  assert.strictEqual(mockStorage["snakeBest"], "10", "die() 必须 persistBest 落盘");
  Snake.close();
  Snake.open();
  assert.strictEqual(T.best(), 10, "往返：再次打开读到落盘的最高分");
  Snake.close();
  delete mockStorage["snakeBest"];
});

test("WB-079 setState 四态文案：start/play/pause/dead 全覆盖", () => {
  Snake.open();
  // start
  assert.strictEqual(elements["veilTitle"].textContent, "准备好出发了吗？");
  assert.strictEqual(elements["veilBtn"].textContent, "出发");
  // play（遮罩收起）
  T.primaryAction();
  assert.strictEqual(T.state(), "play");
  assert.strictEqual(elements["snakeVeil"].style.display, "none");
  // pause
  T.primaryAction();
  assert.strictEqual(T.state(), "pause");
  assert.strictEqual(elements["veilTitle"].textContent, "歇一会儿");
  assert.strictEqual(elements["veilBtn"].textContent, "继续");
  assert.strictEqual(elements["snakeVeil"].style.display, "flex");
  // 回到 play 再撞墙 → dead（0 分非纪录分支）
  T.primaryAction();
  assert.strictEqual(T.state(), "play");
  T.setFood(20, 2);
  let g = 0;
  while (T.state() !== "dead" && g++ < 30) T.step();
  assert.strictEqual(T.state(), "dead");
  assert.strictEqual(elements["veilTitle"].textContent, "这段旅程 · 0 分");
  assert.strictEqual(elements["veilSub"].textContent, "最高 0 分 · 再来一次，你可以的！");
  assert.strictEqual(elements["veilBtn"].textContent, "再来一次");
  Snake.close();
});

test("WB-080 die() 粒子：每蛇身节点生成一枚暖色粒子", () => {
  Snake.open();
  T.setFood(20, 2);
  let g = 0;
  while (T.state() !== "dead" && g++ < 30) T.step();
  assert.strictEqual(T.state(), "dead");
  const ps = T.particles();
  assert.strictEqual(ps.length, 3, "初始蛇长 3——每节点一枚粒子");
  for (const p of ps) {
    assert.ok(p.life > 0, "粒子必须带存活期");
    assert.ok(["#FFF0C4", "#FFCF6E"].includes(p.color), "粒子限定暖色板");
  }
  assert.strictEqual(ps[0].color, "#FFF0C4", "蛇头粒子亮蜜色");
  Snake.close();
});

test("WB-081 DIG 位图覆盖：+ 与 0-9 全部字形可绘制，未知字形静默跳过", () => {
  Snake.open();  // 确保 px/pctx 就绪
  const glyphs = ["+", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  for (const ch of glyphs) {
    const before = fillCalls.length;
    T.drawPixelText(ch, 10, 10, "#FFF6E3");
    assert.ok(fillCalls.length > before, `字形 ${ch} 必须产生 fillRect 绘制`);
  }
  // 未知字形：不绘制、不崩溃（drawPixelText 对缺字形 continue）
  const before2 = fillCalls.length;
  assert.doesNotThrow(() => T.drawPixelText("Z", 10, 10, "#FFF6E3"));
  assert.strictEqual(fillCalls.length, before2, "未知字形不得产生绘制");
  Snake.close();
});

// ═══ WB-133 / WB-151（2026-10-01 审计）——独立干净实例加载器 ═══
// WB-133 的缺陷前提是「页面加载后、首次 open 前」：浮层内联 display 为空串
//（初始隐藏由 CSS 类承担）。共享实例已被前置测试 open/close 过（内联
// display 已是 'none'），无法复现——必须以全新模块实例 + 全新元素桩驱动。
function loadFreshModule(opts) {
  opts = opts || {};
  const storage = opts.storage || {};
  const els = {};
  function freshEl(id) {
    if (!els[id]) {
      els[id] = {
        textContent: "",
        style: { display: "", width: "", height: "" },
        classList: { add: () => {}, remove: () => {} },
        addEventListener: () => {},
        _attrs: {},
        setAttribute(n, v) { this._attrs[n] = String(v); },
        getAttribute(n) { return n in this._attrs ? this._attrs[n] : null; },
        focus: () => {},
      };
    }
    return els[id];
  }
  els["snakeCanvas"] = createMockCanvas();
  // 前置建浮层元素——「首开前」形态断言需要读取其内联 display（空串）
  freshEl("snakeOverlay");
  const listeners = {};
  const doc = {
    getElementById: (id) => (id === "snakeCanvas" ? els["snakeCanvas"] : freshEl(id)),
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
    createElement: (tag) => (tag === "canvas"
      ? createMockCanvas()
      : { style: {}, appendChild: () => {}, addEventListener: () => {} }),
    body: { innerText: "" },
  };
  const win = Object.assign({}, mockGlobal.window);
  delete win.__AEGIS_SNAKE_TEST__;
  if (opts.testFlag) win.__AEGIS_SNAKE_TEST__ = true;
  const sb = Object.assign({}, mockGlobal, {
    document: doc,
    window: win,
    localStorage: {
      getItem: (k) => storage[k] || null,
      setItem: (k, v) => { storage[k] = v; },
    },
    requestAnimationFrame: mockGlobal.requestAnimationFrame,
    cancelAnimationFrame: mockGlobal.cancelAnimationFrame,
  });
  sb.globalThis = sb;
  vm.runInContext(code, vm.createContext(sb), { filename: "start.snake.js" });
  return { Snake: sb.Snake, els, listeners, storage };
}

test("WB-133 加载态 Escape：首开前按键守卫必须挡下，snakeBest 不被 0 覆盖", () => {
  // 缺陷前提：fresh 实例 best=0（loadBest 只在 open 中调用），
  // localStorage 已存 57——旧守卫（判内联 display）此形态放行 Escape
  const fresh = loadFreshModule({ testFlag: true, storage: { snakeBest: "57" } });
  assert.strictEqual(fresh.els["snakeOverlay"].style.display, "",
    "前提：首开前浮层内联 display 为空串（隐藏由 CSS 类承担）");
  const handlers = fresh.listeners["keydown"] || [];
  assert.ok(handlers.length >= 1, "start.snake.js 必须注册 document keydown 守卫");
  handlers.forEach((fn) => fn({ key: "Escape", preventDefault() {} }));
  assert.strictEqual(fresh.storage["snakeBest"], "57",
    "首开前 Escape 必须被 isOpen 守卫挡下——不得以 best=0 覆盖已存最高分");
  // 对照：open 后 Escape 走正常关闭路径——加载后的真实最高分持久化
  fresh.Snake.open();
  assert.strictEqual(fresh.Snake.__test.best(), 57, "open 必须加载既有最高分");
  handlers.forEach((fn) => fn({ key: "Escape", preventDefault() {} }));
  assert.strictEqual(fresh.els["snakeOverlay"].style.display, "none", "开态 Escape 正常关闭");
  assert.strictEqual(fresh.storage["snakeBest"], "57", "正常关闭持久化的是加载后的最高分");
});

// ═══ WB-151（2026-10-01 审计）：__test 钩子条件注入——生产形态零暴露 ═══
test("WB-151 __test 条件注入：未声明测试标志时钩子不得挂载", () => {
  const prod = loadFreshModule({ testFlag: false });
  assert.ok(prod.Snake, "生产形态模块对象必须存在");
  assert.strictEqual(prod.Snake.__test, undefined,
    "未声明 __AEGIS_SNAKE_TEST__ 时受控钩子不得随成品注入");
  assert.strictEqual(typeof prod.Snake.open, "function",
    "open/close 公共 API 不受测试标志影响");
  assert.doesNotThrow(() => { prod.Snake.open(); prod.Snake.close(); },
    "无钩子形态下 open/close 生命周期必须照常");
});

console.log(`\n=== 结果: ${passed} 通过, ${failed} 失败 ===\n`);
if (failed > 0) process.exit(1);

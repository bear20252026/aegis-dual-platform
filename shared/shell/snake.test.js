// 贪吃蛇游戏逻辑回归测试（Node.js 无头运行——Mock DOM 后加载 start.snake.js）
// 每次修改 start.snake.js 后必须运行此文件：node shared/shell/snake.test.js
"use strict";

const assert = require("assert");
const path = require("path");
const fs = require("fs");

// ═══ Mock DOM 环境 ═══
function createMockContext2D() {
  return {
    fillRect: () => {}, clearRect: () => {},
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
  addEventListener: () => {},
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
   "food", "bonus", "setFood", "setBonus"].forEach((k) =>
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

console.log(`\n=== 结果: ${passed} 通过, ${failed} 失败 ===\n`);
if (failed > 0) process.exit(1);

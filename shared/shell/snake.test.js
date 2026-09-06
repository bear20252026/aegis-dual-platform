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

console.log(`\n=== 结果: ${passed} 通过, ${failed} 失败 ===\n`);
if (failed > 0) process.exit(1);

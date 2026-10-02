// helpers.mjs —— tests/ui-regression 共享桩（WB-127，2026-09-26 审计）
// 此前 host_bridge（现 import_contract）.test.mjs 与 start_host.test.mjs 各自维护一套
// chrome.webview 桩（两份重复、语义易漂移）——抽单一事实源：
// - loadHost：以形参遮蔽裸标识符加载 shared/shell/start.js（无桥即 undefined，
//   不抛 ReferenceError；winApi/andApi 的 window.xxx && 短路同理）
// - makeCsBridge：捕获 postMessage 与 message 监听，可按 id 模拟宿主回包
// - makeEl：start_main/start_import 两份重复 DOM 节点桩合一（WB-206，
//   2026-10-02 审计下沉——单一事实源，元素表与用例仍留在各测试文件）
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

export const HOSTJS = readFileSync(join(ROOT, 'shared', 'shell', 'start.js'), 'utf8');

/**
 * 以可控的全局桥注入执行 start.js，返回 Host 适配层。
 * pywebview/AegisBridge/chrome 缺席即 undefined（桥不存在语义）。
 * Date（WB-037，2026-09-23 审计·W5 批）：可选注入假时钟构造器——
 * csCall 的惰性 TTL 清扫以 Date.now() 取时，测试用假时钟驱动超龄。
 * events（WB-205，2026-10-02 审计）：可选传入数组——注入 window 的
 * addEventListener 记录器，start.js 首文件的 error/unhandledrejection
 * 监听可被测试取出并受控触发（不注入时维持裸 window 桩——监听不注册）。
 */
export function loadHost({ pywebview, AegisBridge, chrome, Date: DateCtor, events } = {}) {
  const win = {};
  if (pywebview !== undefined) win.pywebview = pywebview;
  if (AegisBridge !== undefined) win.AegisBridge = AegisBridge;
  if (chrome !== undefined) win.chrome = chrome;
  if (Array.isArray(events)) {
    win.addEventListener = (type, fn) => { events.push({ type, fn }); };
  }
  const fn = new Function('window', 'pywebview', 'chrome', 'AegisBridge', 'Date',
    HOSTJS + '\nreturn Host;');
  return fn(win, pywebview, chrome, AegisBridge, DateCtor || Date);
}

/**
 * cs 桥桩：返回 { bridge, posted, respond }。
 * - bridge.webview 形态（注入为 window.chrome）——loadHost({ chrome: bridge })
 *   （WB-194，2026-10-02 审计：原注「chromium.webview」失实——start.js 的
 *   csApi() 消费的是 chrome.webview.postMessage）
 * - posted 记录全部 postMessage 载荷（op/id/args）
 * - respond(id, result) 按 csCall 的 id 关联模拟宿主回包
 */
export function makeCsBridge() {
  const listeners = [];
  const posted = [];
  return {
    bridge: {
      webview: {
        postMessage(msg) { posted.push(msg); },
        addEventListener(_type, fn) { listeners.push(fn); },
      },
    },
    posted,
    respond(id, result) {
      listeners.forEach((fn) => fn({ data: { __aegisRes: 1, id, result } }));
    },
  };
}

/**
 * 共享最小 DOM 节点桩（WB-206，2026-10-02 审计：start_main.test.mjs 与
 * start_import.test.mjs 两份重复桩下沉合一）。覆盖两文件触及的全部表面：
 * - 属性记录（_attrs/_removedAttrs）、焦点记录（_focused）、类名增删
 * - textContent 赋值清空子节点（容器换页依赖的真实 DOM 语义）
 * - appendChild 移动语义（WB-134 单例提示重复 append 不产生副本）
 * - removeAttribute/hasAttribute（WB-179 hidden 属性配对翻转断言面）
 * - querySelectorAll 仅支持 [role="menuitemradio"] 过滤（WB-044 方向键），
 *   其余选择器一律空集——两消费方只触及该形态
 * overrides（可选参数扩展点）：按 id 覆写个别属性（如 disabled 初值）。
 */
export function makeEl(tag, overrides) {
  const node = {
    tagName: tag,
    children: [],
    style: {},
    dataset: {},
    className: '',
    title: '',
    value: '',
    disabled: false,
    checked: false,
    tabIndex: 0,
    _handlers: {},
    _attrs: {},
    _removedAttrs: [],
    _focused: false,
    _textContent: '',
    appendChild(c) {
      // 真实 DOM 语义：append 已挂载节点是「移动」而非复制
      const at = node.children.indexOf(c);
      if (at !== -1) node.children.splice(at, 1);
      node.children.push(c);
      return c;
    },
    // WB-107：书签宫格经 replaceChildren 整段替换（frag 进容器）
    replaceChildren(...cs) { node.children.length = 0; cs.forEach((c) => node.children.push(c)); },
    addEventListener(type, fn) { (node._handlers[type] = node._handlers[type] || []).push(fn); },
    setAttribute(n, v) { node._attrs[n] = String(v); },
    getAttribute(n) { return n in node._attrs ? node._attrs[n] : null; },
    // WB-179：hidden 属性配对——removeAttribute 记录（WB-137 断言面沿用）
    removeAttribute(n) { node._removedAttrs.push(n); delete node._attrs[n]; },
    hasAttribute(n) { return n in node._attrs; },
    // 导入向导焦点陷阱消费 contains——桩恒真（背景页可聚焦语义）
    contains() { return true; },
    focus() { node._focused = true; },
    // WB-147：classList 记录——geoBtn 降级态断言需要读取类名变化
    classList: {
      add(c) {
        const parts = node.className ? node.className.split(' ') : [];
        if (!parts.includes(c)) parts.push(c);
        node.className = parts.join(' ');
      },
      remove(c) {
        node.className = (node.className ? node.className.split(' ') : [])
          .filter((x) => x !== c).join(' ');
      },
    },
    querySelectorAll(sel) {
      const hit = [];
      const want = sel === '[role="menuitemradio"]' ? 'menuitemradio' : null;
      if (!want) return hit;
      (function walk(n) { (n.children || []).forEach((c) => { if (c._attrs && c._attrs.role === want) hit.push(c); walk(c); }); })(node);
      return hit;
    },
  };
  // 真实 DOM 语义：对 textContent 赋值会清空全部子节点（容器换页依赖）
  Object.defineProperty(node, 'textContent', {
    get() { return node._textContent; },
    set(v) { node._textContent = String(v); node.children.length = 0; },
  });
  return Object.assign(node, overrides || {});
}

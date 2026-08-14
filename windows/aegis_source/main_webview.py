"""main_webview.py —— Aegis 系统内核版入口（Windows: WebView2 / macOS: WKWebView）。

架构：
- pywebview 一个窗口 = 一个系统内核 WebView（Windows 借 Edge WebView2，macOS 借 WKWebView）
- UI 外壳：本地 HTML（shell/start.html）+ 注入式工具栏（每页注入固定顶栏）
- Python 桥：pywebview js_api —— JS 侧通过 `pywebview.api.xxx()` 调 Python

稳定性设计（专家审查 + 逐行加固）：
1. 【核心】js_api 回调运行在 pywebview 的 HTTP 服务线程（Thread-N _call），若在该线程
   同步调用 window.load_url / evaluate_js，winforms 后端会 Invoke 到 UI 线程执行并
   阻塞等待 —— 而 UI 线程又在等待 js_api 的 HTTP 响应返回 → 互相等待 = 死锁，
   表现就是"搜索后页面永远不跳转、界面冻结（像崩溃）"。
   根治：所有窗口操作放入队列，由独立导航线程串行执行；js_api 回调只做纯逻辑
   （更新状态/记历史）立即返回，绝不阻塞等待 UI 线程。
2. 注入走底层 gui.evaluate_js（ExecuteScriptAsync 直注入，不经 eval），
   绕开百度等 CSP 严格站点对 unsafe-eval 的拦截（"标签栏消失"的根因）。
3. 共享状态（_tabs/_current）一律用 RLock 保护；所有 js_api 方法都是「桥边界」，
   任何异常必须被兜住，绝不外泄到 JS/线程。

运行（源码）：
    python main_webview.py
    python main_webview.py --smoke-test   # 无窗口自检：建隐藏窗口→10 秒→退出
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
START_URL = (ROOT / "shell" / "start.html").as_uri()
_DEFAULT_WALLPAPER = "aurora-twilight.jpg"

# 搜索引擎表：key -> (名称, 搜索 URL 模板)
SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "baidu":  ("百度", "https://www.baidu.com/s?wd={}"),
    "bing":   ("必应", "https://www.bing.com/search?q={}"),
    "google": ("谷歌", "https://www.google.com/search?q={}"),
    "sogou":  ("搜狗", "https://www.sogou.com/web?query={}"),
}
DEFAULT_ENGINE = "baidu"

# 注入式工具栏：单行紧凑设计（苹果风格）。
# - 高度 40px，毛玻璃半透明深蓝紫（与 aurora 壁纸同色系），白色文字
# - 左侧标签条（紧凑胶囊）+ 新建标签 + 后退/前进/刷新/主页 + 地址栏
# Python 侧把标签数据（__TABS_JSON__）与当前网址（__AEGIS_URL__）直接内嵌进脚本，
# 一次 evaluate_js 完成渲染 —— 零 HTTP 往返（卡顿主要来源已被消除）。
# 整个 IIFE 自身 try/catch：任何页面（含 CSP 严格站点、无 body 的空白页）都不允许
# 因注入脚本抛错而中断。
TOOLBAR_JS = r"""
(function () {
  try {
    if (document.getElementById('aegis-chrome')) return;
    var TABS_DATA = __TABS_JSON__;
    var bar = document.createElement('div');
    bar.id = 'aegis-chrome';
    bar.style.cssText = [
      'position:fixed','top:0','left:0','right:0','height:40px','z-index:2147483647',
      'display:flex','align-items:center','gap:4px','padding:0 8px',
      'background:linear-gradient(180deg,rgba(40,34,78,0.86),rgba(28,24,62,0.84))',
      'backdrop-filter:blur(16px) saturate(150%)',
      '-webkit-backdrop-filter:blur(16px) saturate(150%)',
      'border-bottom:1px solid rgba(255,255,255,0.14)',
      'box-shadow:0 2px 12px rgba(15,10,40,0.35)','box-sizing:border-box',
      'font-family:system-ui,-apple-system,"SF Pro Text","Segoe UI",sans-serif'
    ].join(';');

    // —— 标签条（紧凑胶囊，限宽省略）——
    var tabsWrap = document.createElement('div');
    tabsWrap.style.cssText = 'display:flex;align-items:center;gap:3px;height:28px;' +
      'overflow:hidden;flex:0 1 auto;min-width:0;max-width:55%;';
    bar.appendChild(tabsWrap);

    var tabs = (TABS_DATA && TABS_DATA.tabs) || [];
    var cur = (TABS_DATA && TABS_DATA.current) || 0;
    for (var i = 0; i < tabs.length; i++) {
      (function (idx) {
        var t = document.createElement('div');
        t.style.cssText = 'display:inline-flex;align-items:center;gap:4px;max-width:120px;height:26px;' +
          'padding:0 4px 0 10px;border-radius:7px;cursor:pointer;font-size:11px;color:rgba(255,255,255,0.72);' +
          'background:' + (idx === cur ? 'rgba(255,255,255,0.18)' : 'transparent') + ';' +
          'border:1px solid ' + (idx === cur ? 'rgba(255,255,255,0.22)' : 'transparent') + ';';
        var label = document.createElement('span');
        label.textContent = (tabs[idx] && tabs[idx].title) || '新标签页';
        label.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff;';
        var x = document.createElement('span');
        x.textContent = '\u00d7';
        x.style.cssText = 'width:15px;height:15px;line-height:13px;text-align:center;border-radius:50%;' +
          'cursor:pointer;color:rgba(255,255,255,0.65);font-size:12px;flex:0 0 auto;';
        x.onmouseenter = function(){ x.style.background = 'rgba(255,255,255,0.25)'; };
        x.onmouseleave = function(){ x.style.background = 'transparent'; };
        x.onclick = function (e) {
          e.stopPropagation();
          try { if (window.pywebview && pywebview.api) pywebview.api.close_tab(idx); } catch (err) {}
        };
        t.appendChild(label);
        t.appendChild(x);
        t.onclick = function () {
          if (idx !== cur && window.pywebview && pywebview.api) {
            try { pywebview.api.switch_tab(idx); } catch (err) {}
          }
        };
        tabsWrap.appendChild(t);
      })(i);
    }
    var nb = document.createElement('div');
    nb.textContent = '+';
    nb.title = '新标签页';
    nb.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;' +
      'width:24px;height:24px;border-radius:7px;cursor:pointer;color:rgba(255,255,255,0.8);font-size:15px;' +
      'flex:0 0 auto;';
    nb.onmouseenter = function(){ nb.style.background = 'rgba(255,255,255,0.16)'; };
    nb.onmouseleave = function(){ nb.style.background = 'transparent'; };
    nb.onclick = function () {
      try { if (window.pywebview && pywebview.api) pywebview.api.new_tab(); } catch (err) {}
    };
    tabsWrap.appendChild(nb);

    // —— 导航按钮 ——
    function btn(glyph, title, act) {
      var b = document.createElement('button');
      b.textContent = glyph; b.title = title;
      b.style.cssText = 'width:26px;height:26px;border:0;background:transparent;border-radius:7px;' +
        'font-size:13px;cursor:pointer;color:rgba(255,255,255,0.85);flex:0 0 auto;line-height:1;';
      b.onmouseenter = function(){ b.style.background = 'rgba(255,255,255,0.16)'; };
      b.onmouseleave = function(){ b.style.background = 'transparent'; };
      b.onclick = function(){
        try { if (window.pywebview && pywebview.api) pywebview.api[act](); } catch (e) {}
      };
      bar.appendChild(b);
      return b;
    }
    btn('\u2190', '后退', 'go_back');
    btn('\u2192', '前进', 'go_forward');
    btn('\u21bb', '刷新', 'reload_page');
    btn('\u2302', '主页', 'go_home');

    // —— 地址栏 ——
    var inp = document.createElement('input');
    inp.id = 'aegis-url';
    inp.spellcheck = false;
    inp.value = '__AEGIS_URL__';
    inp.style.cssText = 'flex:1;min-width:0;height:28px;border:1px solid rgba(255,255,255,0.18);' +
      'border-radius:14px;padding:0 12px;font-size:12px;outline:none;' +
      'background:rgba(255,255,255,0.14);color:#fff;';
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && window.pywebview && pywebview.api) {
        try { pywebview.api.navigate(inp.value); } catch (err) {}
      }
    });
    bar.appendChild(inp);

    var root = document.documentElement || document;
    root.appendChild(bar);
    if (document.body) document.body.style.marginTop = '40px';

    // —— JS 错误上报：页面任何 JS 异常 → Python 日志（后台静默）——
    if (window.pywebview && pywebview.api && !window.__aegis_err_hooked) {
      window.__aegis_err_hooked = true;
      window.addEventListener('error', function (e) {
        try {
          pywebview.api.js_error(
            e.message || 'unknown', e.filename || '', e.lineno, e.colno,
            (e.error && e.error.stack) || ''
          );
        } catch (err) {}
      });
      window.addEventListener('unhandledrejection', function (e) {
        try {
          pywebview.api.js_error(
            'Promise rejection: ' + (e.reason || ''), '', 0, 0,
            (e.reason && e.reason.stack) || ''
          );
        } catch (err) {}
      });
    }
  } catch (e) { /* 注入失败绝不影响页面本身 */ }
})();
"""


class Api:
    """暴露给 JS 的 Python 桥。JS 侧调用 pywebview.api.navigate(...) 等。

    线程约定（关键）：
    - js_api 方法在 pywebview 的 HTTP 服务线程被调用（Thread-N _call）；
    - events.loaded 回调在后台线程被调用；
    - 因此**所有窗口操作（load_url / evaluate_js）绝不在此类线程同步执行**，
      统一投递到 self._nav_q，由独立导航线程串行消费 —— 避免 Invoke 死锁。
    - 共享状态用 self._lock（RLock）保护。

    递归崩溃修复（crash_reports 线程栈铁证：get_functions 无限递归 834 层）：
    pywebview 注入 js_api 时用 dir(obj) 遍历本对象所有属性并递归扫描，
    而 self.window 等公开属性指向含循环引用的 pywebview Window 对象树，
    导致注入线程无限递归卡死（表现为"页面内二次跳转链接后未响应"）。
    因此重写 __dir__ 只暴露 js_api 方法白名单 —— get_functions 只看到方法，
    永不递归进对象属性。
    """

    # 暴露给 JS 的方法白名单（其余属性/内部方法一律对 dir() 隐藏）
    _JS_EXPOSED = frozenset({
        "get_wallpaper", "set_wallpaper",
        "get_search_engine", "set_search_engine",
        "get_tabs", "new_tab", "switch_tab", "close_tab",
        "navigate", "go_back", "go_forward", "reload_page", "go_home",
        "current_url", "js_error",
        "get_bookmarks", "add_bookmark", "remove_bookmark",
        "get_history", "get_most_visited",
    })

    def __dir__(self) -> list[str]:
        """只暴露 js_api 方法白名单，阻断 pywebview get_functions 的对象树递归。"""
        return sorted(self._JS_EXPOSED)

    def __init__(self) -> None:
        self.window: Any = None   # create_window 之后由 main() 绑定
        self.bookmarks: Any = None
        self.history: Any = None
        self.config: Any = None
        self._data_dir: str = ""
        self._lock = threading.RLock()
        self._tabs: list[dict[str, str]] = [{"title": "新标签页", "url": START_URL}]
        self._current: int = 0
        self._engine: str = DEFAULT_ENGINE
        # 导航队列 + 常驻消费线程（窗口操作只在这里执行）
        self._nav_q: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._nav_thread: threading.Thread | None = None
        self._nav_stop = False

    # ================= 导航线程（唯一执行窗口操作的地方） =================
    def _ensure_nav_thread(self) -> None:
        with self._lock:
            if self._nav_thread is not None and self._nav_thread.is_alive():
                return
            self._nav_stop = False
            t = threading.Thread(target=self._nav_loop, name="aegis-nav", daemon=True)
            t.start()
            self._nav_thread = t

    def _nav_loop(self) -> None:
        while not self._nav_stop:
            try:
                item = self._nav_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            action, arg = item
            w = self.window
            if w is None:
                continue
            try:
                if action == "load":
                    self._run_with_timeout(
                        lambda w=w, arg=arg: w.load_url(arg), "load_url")
                elif action == "eval":
                    self._run_with_timeout(
                        lambda w=w, arg=arg: self._exec_script_impl(w, arg),
                        "evaluate_js")
            except Exception:
                pass  # 窗口销毁竞态 / WebView 不可用时静默

    def _run_with_timeout(self, fn, name: str, timeout: float = 6.0) -> bool:
        """在独立线程执行窗口操作，超时即放弃并留痕 —— 防止 evaluate_js 的
        semaphore.acquire() 因页面导航/销毁竞态无限阻塞导航线程（"未响应"根因）。"""
        done = threading.Event()

        def _worker() -> None:
            try:
                fn()
            except Exception:
                pass
            finally:
                done.set()

        try:
            t = threading.Thread(target=_worker, daemon=True, name=f"aegis-op-{name}")
            t.start()
        except Exception:
            return False
        if done.wait(timeout):
            return True
        # 超时：窗口操作未返回（WebView 忙/卡），放弃并记录，绝不阻塞导航线程
        try:
            from crash_reporter import dump_threads_to_report, log_event
            log_event(f"导航操作超时被放弃: {name} ({timeout}s)")
            dump_threads_to_report(f"nav-op-timeout:{name}")
        except Exception:
            pass
        return False

    def _exec_script_impl(self, w: Any, script: str) -> None:
        """在导航线程执行 JS。优先底层 gui.evaluate_js（ExecuteScriptAsync 直注入，
        不经 eval，不受 CSP 限制）；失败回退标准 evaluate_js。"""
        gui = getattr(w, "gui", None)
        if gui is not None:
            try:
                gui_eval = getattr(gui, "evaluate_js", None)
                if gui_eval is not None:
                    uid = getattr(w, "uid", "")
                    try:
                        gui_eval(script, uid, True)
                        return
                    except TypeError:
                        gui_eval(script)
                        return
            except Exception:
                pass
        try:
            w.evaluate_js(script)
        except Exception:
            pass

    def _load(self, url: str) -> bool:
        """投递导航请求，立即返回（绝不在 js_api 线程同步 load_url）。"""
        if not url:
            return False
        try:
            self._ensure_nav_thread()
            self._nav_q.put(("load", url))
            return True
        except Exception:
            return False

    def _eval(self, script: str) -> bool:
        """投递 JS 注入请求，立即返回。"""
        if not script:
            return False
        try:
            self._ensure_nav_thread()
            self._nav_q.put(("eval", script))
            return True
        except Exception:
            return False

    def _tabs_snapshot(self) -> dict:
        """线程安全地返回标签快照（副本，避免调用方拿到活引用）。"""
        with self._lock:
            tabs = [dict(t) for t in self._tabs]
            current = self._current
        return {"tabs": tabs, "current": current}

    # ================= 壁纸 =================
    def get_wallpaper(self) -> str:
        """返回当前新标签页壁纸文件名（配置持久化）。"""
        try:
            if self.config is not None:
                name = getattr(self.config, "ntp_wallpaper", "") or ""
                if name:
                    return name
        except Exception:
            pass
        return _DEFAULT_WALLPAPER

    def set_wallpaper(self, name: str) -> None:
        """切换壁纸并持久化（白名单校验）。"""
        try:
            from app.asset_scheme import WALLPAPERS
            if not name or name not in WALLPAPERS:
                return
            if self.config is None:
                from app.config import AppConfig
                self.config = AppConfig()
            self.config.ntp_wallpaper = name
            if self._data_dir:
                self.config.save(self._data_dir)
        except Exception:
            pass  # 壁纸配置失败不影响浏览

    # ================= 搜索引擎 =================
    def get_search_engine(self) -> dict:
        """返回 {engine, engines:[{key,name}]}。"""
        return {
            "engine": self._engine,
            "engines": [{"key": k, "name": v[0]} for k, v in SEARCH_ENGINES.items()],
        }

    def set_search_engine(self, key: str) -> None:
        """切换搜索引擎并持久化（白名单校验）。"""
        try:
            if key not in SEARCH_ENGINES:
                return
            self._engine = key
            if self.config is None:
                from app.config import AppConfig
                self.config = AppConfig()
            self.config.engine = key
            if self._data_dir:
                self.config.save(self._data_dir)
        except Exception:
            pass  # 配置失败不影响本次切换

    # ================= 标签页 =================
    def get_tabs(self) -> dict:
        """返回 {tabs:[{title,url}], current:int}（快照）。"""
        return self._tabs_snapshot()

    def new_tab(self, url: str = "") -> None:
        target = normalize_url(url) if url else START_URL
        with self._lock:
            self._tabs.append({"title": "新标签页", "url": target})
            self._current = len(self._tabs) - 1
        self._load(target)

    def switch_tab(self, index: Any) -> None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        with self._lock:
            if not (0 <= index < len(self._tabs)):
                return
            self._current = index
            url = self._tabs[index]["url"]
        self._load(url)

    def close_tab(self, index: Any) -> None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        with self._lock:
            if len(self._tabs) <= 1 or not (0 <= index < len(self._tabs)):
                return
            self._tabs.pop(index)
            if self._current >= index and self._current > 0:
                self._current -= 1
            url = self._tabs[self._current]["url"]
        self._load(url)

    def _update_current(self, url: str, title: str = "") -> None:
        """页面加载后刷新当前标签的 url/title（线程安全）。"""
        if not url and not title:
            return
        with self._lock:
            if 0 <= self._current < len(self._tabs):
                if url:
                    self._tabs[self._current]["url"] = url
                if title:
                    self._tabs[self._current]["title"] = title[:80]

    # ================= 导航 =================
    def navigate(self, text: str) -> None:
        url = normalize_url(text, self._engine)
        try:
            if self.history is not None:
                self.history.add(url, text)
        except Exception:
            pass  # 历史写入失败不影响导航
        self._update_current(url, text)
        self._load(url)

    def go_back(self) -> None:
        self._eval("history.back()")

    def go_forward(self) -> None:
        self._eval("history.forward()")

    def reload_page(self) -> None:
        self._eval("location.reload()")

    def go_home(self) -> None:
        self._load(START_URL)

    # ---- 状态 ----
    def current_url(self) -> str:
        w = self.window
        if w is None:
            return ""
        try:
            return w.get_current_url() or ""
        except Exception:
            return ""

    # ================= 健康检查（供看门狗调用，绝不含窗口操作） =================
    def _nav_healthy(self) -> bool:
        """导航线程健康度：队列积压不爆炸、导航线程存活。"""
        try:
            if self._nav_q.qsize() > 50:
                return False  # 队列积压 = 导航线程可能卡死
            with self._lock:
                t = self._nav_thread
                if t is None:
                    return False
                return t.is_alive()
        except Exception:
            return False

    def _recover_nav(self) -> None:
        """导航线程疑似卡死时：清空队列并重启（尽力恢复，绝不阻塞）。"""
        try:
            while not self._nav_q.empty():
                try:
                    self._nav_q.get_nowait()
                except queue.Empty:
                    break
            with self._lock:
                self._nav_stop = True
                self._nav_thread = None
            # 重启导航线程
            self._ensure_nav_thread()
            from crash_reporter import log_event
            log_event("看门狗：导航线程疑似卡死，已重启")
        except Exception:
            pass

    # ---- JS 错误上报（JS 侧 window.onerror / unhandledrejection → 这里）----
    def js_error(self, message: str, source: str = "", line: Any = None,
                 col: Any = None, stack: str = "") -> None:
        """接收页面 JS 错误，写入崩溃报告 events.log（后台静默）。"""
        try:
            from crash_reporter import log_event
            line = int(line) if line else ""
            col = int(col) if col else ""
            log_event(
                f"JS错误: {str(message)[:200]} | src={str(source)[:120]} "
                f"@{line}:{col} | stack={str(stack)[:300]}"
            )
        except Exception:
            pass  # 日志失败绝不影响页面

    # ================= 书签 =================
    def get_bookmarks(self) -> list:
        """返回书签列表 [{id,title,url}]。"""
        try:
            if self.bookmarks is None:
                return []
            rows = self.bookmarks.all()
            return [{"id": r[0], "title": r[1], "url": r[2]} for r in rows]
        except Exception:
            return []

    def add_bookmark(self, title: str, url: str) -> bool:
        try:
            if self.bookmarks is not None:
                return self.bookmarks.add(title, url)
        except Exception:
            pass
        return False

    def remove_bookmark(self, url: str) -> None:
        try:
            if self.bookmarks is not None:
                self.bookmarks.remove(url)
        except Exception:
            pass

    # ================= 历史 =================
    def get_history(self, limit: Any = 100) -> list:
        """返回历史 [{id,url,title,time}]。"""
        try:
            if self.history is None:
                return []
            n = int(limit) if limit else 100
            rows = self.history.all(n)
            return [
                {"id": r[0], "url": r[1], "title": r[2], "time": r[3]}
                for r in rows
            ]
        except Exception:
            return []

    def get_most_visited(self, limit: Any = 12) -> list:
        try:
            if self.history is None:
                return []
            n = int(limit) if limit else 12
            rows = self.history.most_visited(n)
            return [{"id": r[0], "url": r[1], "title": r[2]} for r in rows]
        except Exception:
            return []


def normalize_url(text: str | None, engine: str = DEFAULT_ENGINE) -> str:
    """把用户输入变成可导航 URL：无协议补 https://，非网址当搜索词（用当前引擎）。"""
    text = (text or "").strip()
    if not text:
        return START_URL
    if text == "about:blank":
        return "about:blank"
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "file://")):
        return text
    # 含空格或没有点号 → 视为搜索
    if " " in text or "." not in text:
        template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES[DEFAULT_ENGINE])[1]
        return template.format(urllib.parse.quote(text))
    return "https://" + text


def on_loaded(window: Any, api: Api) -> None:
    """每页加载完成后：刷新当前标签 url/title，并注入工具栏（含新标签页）。

    注意：该回调在 pywebview 的后台线程中执行；本函数自身绝不抛异常。
    get_current_url 属于只读查询（winforms 后端线程安全），可直接调用；
    注入（evaluate_js）统一走 api._eval 投递到导航线程执行。
    """
    if window is None or api is None:
        return
    try:
        url = window.get_current_url() or ""
    except Exception:
        url = ""
    api._update_current(url)
    try:
        # 内嵌标签数据 → 单次注入，零 HTTP 往返。
        js = (
            TOOLBAR_JS
            .replace("__AEGIS_URL__", json.dumps(url))
            .replace("__TABS_JSON__", json.dumps(api.get_tabs()))
        )
        api._eval(js)
    except Exception:
        pass  # 页面不允许注入（CSP 严格站点 / 空白页）时静默降级


def main() -> int:
    import webview

    # 关键：新窗口请求（target=_blank 链接）必须在当前窗口打开，
    # 而不是交给系统默认浏览器（默认 True 会导致点百度热搜跳去谷歌浏览器）。
    try:
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
    except Exception:
        pass

    # 崩溃报告收集器：任何线程未捕获异常 → 写入 crash_reports/（后台静默，绝不弹窗）
    try:
        from crash_reporter import install_crash_reporter
        data_dir0 = ""
        try:
            from app.paths import resolve_data_dir
            data_dir0 = resolve_data_dir()
        except Exception:
            pass
        install_crash_reporter(data_dir0 or None)
    except Exception:
        pass

    if "--smoke-test" in sys.argv:
        return _smoke_test(webview)

    api = Api()
    try:
        from app.bookmark_store import BookmarkStore
        from app.config import AppConfig
        from app.history_store import HistoryStore
        from app.paths import resolve_data_dir
        data_dir = resolve_data_dir()
        api._data_dir = data_dir
        api.bookmarks = BookmarkStore(data_dir)
        api.history = HistoryStore(data_dir)
        api.config = AppConfig.load(data_dir)
        if api.config is not None:
            eng = getattr(api.config, "engine", "") or ""
            if eng in SEARCH_ENGINES:
                api._engine = eng
    except Exception:
        pass  # 书签/历史/配置不可用时降级为纯浏览

    window = webview.create_window(
        "Aegis 安全浏览器",
        url=START_URL,
        js_api=api,          # js_api 必须在 create_window 时传入（renderer 从 _js_api 读取）
        width=1280,
        height=820,
        min_size=(900, 600),
    )
    if window is None:
        print("[fatal] create_window 返回 None，无法启动", file=sys.stderr)
        return 1
    api.window = window      # 创建后再绑定 window 引用，供桥方法调用
    window.events.loaded += lambda: on_loaded(window, api)

    # 看门狗：监控导航线程健康度，疑似卡死 → dump 线程栈 + 自动重启导航线程
    try:
        from crash_reporter import dump_threads_to_report, log_event, start_watchdog
        healthy = {
            "recover_count": 0,
            "last_dump": 0.0,
        }

        def _watch() -> bool:
            ok = api._nav_healthy()
            if not ok:
                api._recover_nav()
                healthy["recover_count"] += 1
                # 立即 dump 线程栈（限流：60 秒内最多一次），
                # 确保"未响应"现场必然留下报告 —— 不能等 bad 计数（恢复太快会重置它）
                import time as _t
                now = _t.monotonic()
                if now - healthy["last_dump"] > 60.0:
                    healthy["last_dump"] = now
                    try:
                        dump_threads_to_report("看门狗：导航线程疑似卡死")
                    except Exception:
                        pass
                try:
                    log_event(f"看门狗：导航线程疑似卡死，已重启（第 {healthy['recover_count']} 次）")
                except Exception:
                    pass
            return ok

        start_watchdog(_watch, interval=2.0, timeout=4.0, name="nav")
    except Exception:
        pass  # 看门狗不可用时降级

    webview.start()
    return 0


def _smoke_test(webview: Any) -> int:
    """无窗口自检：确认系统内核 WebView 能创建并加载真实页面后自动退出。"""
    import time

    result: dict[str, Any] = {"loaded": False, "url": None, "err": ""}
    w = webview.create_window(
        "Aegis smoke", url=START_URL, width=500, height=360, hidden=True,
    )
    if w is None:
        print("[smoke] FAIL — create_window 返回 None")
        return 1

    def on_loaded() -> None:
        result["loaded"] = True
        try:
            result["url"] = w.get_current_url()
        except Exception as e:
            result["err"] = repr(e)
        for ww in list(webview.windows):
            try:
                ww.destroy()
            except Exception:
                pass

    w.events.loaded += on_loaded

    def fallback() -> None:
        time.sleep(10)
        if not result["loaded"]:
            result["err"] = "loaded 事件 10 秒内未触发"
            for ww in list(webview.windows):
                try:
                    ww.destroy()
                except Exception:
                    pass

    threading.Timer(1.0, fallback).start()
    webview.start()
    if result.get("loaded"):
        print(f"[smoke] OK — 系统内核 WebView 可用（loaded: {result.get('url')!r}）")
        return 0
    print(f"[smoke] FAIL — {result.get('err') or 'unknown'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

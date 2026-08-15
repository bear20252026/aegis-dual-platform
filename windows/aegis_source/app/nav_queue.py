"""nav_queue.py —— 导航线程队列（单文件单职责）。

职责：把 pywebview 窗口操作（load_url / evaluate_js）从 js_api 回调线程
中剥离，统一投递到**独立导航线程**串行执行。这是根治以下两类问题的
基础设施（原 main_webview.py 逻辑原样迁移，行为零变化）：

1. 【核心】js_api 回调运行在 pywebview 的 HTTP 服务线程（Thread-N _call），
   若在该线程同步调用 window.load_url / evaluate_js，winforms 后端会
   Invoke 到 UI 线程执行并阻塞等待 —— 而 UI 线程又在等待 js_api 的
   HTTP 响应返回 → 互相等待 = 死锁，表现就是"搜索后页面永远不跳转、
   界面冻结（像崩溃）"。
2. evaluate_js 可能因页面导航/销毁竞态无限阻塞（semaphore.acquire()），
   因此每个窗口操作用独立工作线程 + 超时放弃，绝不阻塞导航线程。

本类不依赖 Qt / pywebview 具体类型（window 为鸭子类型），可离线单测。
"""

import queue
import threading
from collections.abc import Callable
from functools import partial
from typing import Any


def _load_url_op(w: Any, url: str) -> None:
    """模块级辅助：执行 load_url（独立函数，mypy 可推断参数类型）。"""
    w.load_url(url)


class NavQueue:
    """导航线程队列：所有窗口操作串行执行，杜绝 js_api 线程死锁。

    使用方式（由 Api 桥持有）：
        nav = NavQueue()
        nav.bind_window(window)          # create_window 之后绑定
        nav.load("https://...")          # 投递导航，立即返回
        nav.eval("window.history.back()")
    """

    def __init__(self) -> None:
        self.window: Any = None          # create_window 之后由 bind_window 绑定
        self._lock = threading.RLock()
        self._nav_q: queue.Queue = queue.Queue()
        self._nav_thread: threading.Thread | None = None
        self._nav_stop = False

    # ------------------------------------------------------------------ #
    # 绑定 / 投递
    # ------------------------------------------------------------------ #
    def bind_window(self, window: Any) -> None:
        """绑定窗口引用（必须在 create_window 之后调用）。"""
        self.window = window

    def load(self, url: str) -> bool:
        """投递导航请求，立即返回（绝不在 js_api 线程同步 load_url）。"""
        if not url:
            return False
        try:
            self._ensure_thread()
            self._nav_q.put(("load", url))
            return True
        except Exception:
            return False

    def eval(self, script: str) -> bool:
        """投递 JS 注入请求，立即返回。"""
        if not script:
            return False
        try:
            self._ensure_thread()
            self._nav_q.put(("eval", script))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # 导航线程
    # ------------------------------------------------------------------ #
    def _ensure_thread(self) -> None:
        with self._lock:
            if self._nav_thread is not None and self._nav_thread.is_alive():
                return
            self._nav_stop = False
            t = threading.Thread(target=self._nav_loop,
                                 name="aegis-nav", daemon=True)
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
                        partial(_load_url_op, w, arg), "load_url")
                elif action == "eval":
                    self._run_with_timeout(
                        partial(self._exec_script_impl, w, arg),
                        "evaluate_js")
            except Exception:
                pass  # 窗口销毁竞态 / WebView 不可用时静默

    # ------------------------------------------------------------------ #
    # 单次窗口操作：独立工作线程 + 超时放弃
    # ------------------------------------------------------------------ #
    def _run_with_timeout(self, fn: Callable[[], None], name: str,
                          timeout: float = 6.0) -> bool:
        """在独立线程执行窗口操作，超时即放弃并留痕。

        防止 evaluate_js 的 semaphore.acquire() 因页面导航/销毁竞态
        无限阻塞导航线程（"未响应"根因）。
        """
        done = threading.Event()

        def _worker() -> None:
            try:
                fn()
            except Exception:
                pass
            finally:
                done.set()

        try:
            t = threading.Thread(target=_worker, daemon=True,
                                 name=f"aegis-op-{name}")
            t.start()
        except Exception:
            return False
        if done.wait(timeout):
            return True
        # 超时：窗口操作未返回（WebView 忙/卡），放弃并记录，绝不阻塞导航线程
        try:
            from app.event_log import log_event
            from crash_reporter import dump_threads_to_report
            log_event(f"导航操作超时被放弃: {name} ({timeout}s)")
            dump_threads_to_report(f"nav-op-timeout:{name}")
        except Exception:
            pass
        return False

    def _exec_script_impl(self, w: Any, script: str) -> None:
        """在导航线程执行 JS。

        优先底层 gui.evaluate_js（ExecuteScriptAsync 直注入，不经 eval，
        不受 CSP 限制）；失败回退标准 evaluate_js。
        """
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

    # ------------------------------------------------------------------ #
    # 健康检查 / 看门狗（供外部看门狗调用，绝不含窗口操作）
    # ------------------------------------------------------------------ #
    def healthy(self) -> bool:
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

    def recover(self) -> None:
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
            self._ensure_thread()
            from app.event_log import log_event
            log_event("看门狗：导航线程疑似卡死，已重启")
        except Exception:
            pass

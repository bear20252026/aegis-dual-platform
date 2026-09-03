"""main_webview.py —— Aegis 入口（薄壳，仅负责启动组装）。

架构（S1 拆分后）：
- 本文件只做四件事：解析参数、创建窗口、绑定 Api 桥、启动看门狗。
- 业务逻辑已按单一职责拆分到 app/ 下：
    app/shell_toolbar.py  注入式工具栏脚本（TOOLBAR_JS + 渲染）
    app/nav_queue.py      导航线程队列（窗口操作串行化，防死锁）
    app/api_bridge.py     js_api 桥（标签/导航/书签/历史/壁纸/搜索）
- 本文件不 import Qt；webview 延迟导入（仅 main() 运行时）。

运行（源码）：
    python main_webview.py
    python main_webview.py --smoke-test   # 无窗口自检：建隐藏窗口→10 秒→退出
"""

from __future__ import annotations

import sys
import threading
from typing import Any

from app.api_bridge import SEARCH_ENGINES, START_URL, Api, on_loaded

# P0-1 时序修复（全面审计 2026-09-04）：post-start 原生层挂接随迁至
# app/native_hardening.py（加固设置束）/ app/native_interception.py
# （新窗口门禁 + 挂接编排）/ app/native_monitoring.py（探测监控 + 崩溃监听）
from app.native_interception import (
    gate_window_open as _gate_window_open,
)
from app.native_interception import (
    post_start_setup as _post_start_setup,
)



def main() -> int:
    """启动编排（H-3：340 行主线拆为阶段函数——每段职责单一、可独立测试）。

    P0-1 时序修复（全面审计 2026-09-04）：全部原生挂接（拦截/加固/监听）
    从「shell.start() 之前」移到 start(func) 回调——原时序下窗口尚未创建
    （window.native 不存在、CoreWebView2 未初始化），整层加固静默 no-op。
    挂接实现随迁 app/native_{hardening,interception,monitoring}.py
    （本文件只保留启动编排）。
    """
    shell = _init_shell_and_reporter()
    if "--smoke-test" in sys.argv:
        return _smoke_test(shell)
    api, restored_url = _init_stores_and_session()
    window = _create_window(api, shell, restored_url)
    if window is None:
        return 1
    # P0-2 修复：新窗口（window.open/target=_blank）原生门禁。类级替换
    # pywebview 处理器——必须先于 shell.start()（先于任何 EdgeChrome 实例
    # 创建），确定性与 pywebview 自身订阅时序无关。
    window_gate_ok = _gate_window_open()
    # 事件订阅在 start 前完成（pywebview Event 对象随窗口创建即可订阅）
    window.events.loaded += lambda: on_loaded(window, api)
    _start_watchdog(api)

    def _post_start() -> None:
        """start(func) 回调：GUI 循环已启动、窗口已创建后的原生层挂接。"""
        _post_start_setup(window, shell, api, window_gate_ok)

    shell.start(func=_post_start)
    return 0



def _init_shell_and_reporter():
    """壳抽象获取 + 外链设置 + 崩溃报告安装（411-438 段迁移）。"""
    # 壳抽象（禁止被困原则落地，2026-08-15）：通过 shell_adapter 获取
    # 壳实现，默认 pywebview；pytauri 为可插拔实现（壳可随时替换，
    # 业务 api_bridge/nav_queue 等零影响）。pywebview 为运行时依赖。
    from app.shell_adapter import get_shell
    shell = get_shell()  # 默认 pywebview（配置/参数可切 pytauri）

    # 关键：新窗口请求（target=_blank 链接）必须在当前窗口打开，
    # 而不是交给系统默认浏览器（默认 True 会导致点百度热搜跳去谷歌浏览器）。
    # 注意：shell.settings() 返回副本——直接修改 pywebview 模块的 settings 才生效。
    try:
        import webview as _wv_mod
        _wv_mod.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
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
    return shell


def _init_stores_and_session():
    """构建 Api + 存储/配置装载 + 会话恢复（443-492 段迁移）。

    返回 (api, restored_url)——restored_url 为空表示回退默认启动页。
    """
    api = Api()
    try:
        from app.bookmark_store import BookmarkStore
        from app.config import AppConfig
        from app.history_store import HistoryStore
        from app.paths import resolve_data_dir
        data_dir = resolve_data_dir()
        api._data_dir = data_dir
        api.bookmarks = BookmarkStore(data_dir)
        # 预置书签种子（首次启动空库时注入「几何画板」等外挂入口——幂等）
        try:
            api.bookmarks.seed_defaults()
        except Exception:
            pass  # 种子注入失败不影响浏览
        api.history = HistoryStore(data_dir)
        api.config = AppConfig.load(data_dir)
        if api.config is not None:
            eng = getattr(api.config, "engine", "") or ""
            if eng in SEARCH_ENGINES:
                api._engine = eng
    except Exception:
        pass  # 书签/历史/配置不可用时降级为纯浏览

    # 启动恢复上次会话（CHANGELOG Planned：会话恢复；config.resume_session
    # 开启时生效）。恢复失败静默回退默认启动页——绝不阻断浏览启动。
    restored_url = ""
    try:
        if api.config is not None and bool(
                getattr(api.config, "resume_session", False)):
            from app.session_store import SessionStore
            _session_dir = ""
            try:
                from app.paths import resolve_data_dir
                _session_dir = resolve_data_dir()
            except Exception:
                _session_dir = ""
            data = SessionStore(_session_dir).load()
            if data:
                restored_url = api.seed_session(
                    data["tabs"], data.get("current", 0))
                if restored_url:
                    try:
                        from crash_reporter import log_event
                        log_event(
                            f"[session] 已恢复上次会话（{len(data['tabs'])} 个标签）")
                    except Exception:
                        pass
    except Exception:
        restored_url = ""
        pass  # 会话恢复失败静默——回退默认启动页
    return api, restored_url


def _create_window(api, shell, restored_url):
    """创建主窗口并绑定桥引用（494-505 段迁移）。返回 None=失败。"""
    window = shell.create_window(
        api,
        restored_url or START_URL,
        title="Aegis 安全浏览器",
        width=1280,
        height=820,
        min_size=(900, 600),
    )
    if window is None:
        print("[fatal] create_window 返回 None，无法启动", file=sys.stderr)
        return None  # M-1 修复（审计 2026-08-31）：原误 return 1，调用方
                     # `if window is None` 永不触发，导致后续 AttributeError
    api.window = window      # 创建后再绑定 window 引用，供桥方法调用
    return window



def _start_watchdog(api):
    """导航线程看门狗（713-744 段迁移）。"""
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


def _smoke_test(shell: Any) -> int:
    """无窗口自检：确认系统内核 WebView 能创建并加载真实页面后自动退出。"""
    import time

    result: dict[str, Any] = {"loaded": False, "url": None, "err": ""}
    w = shell.create_window(
        None, START_URL, title="Aegis smoke", width=500, height=360, hidden=True,
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
        for ww in shell.windows():
            try:
                ww.destroy()
            except Exception:
                pass

    w.events.loaded += on_loaded

    def fallback() -> None:
        time.sleep(10)
        if not result["loaded"]:
            result["err"] = "loaded 事件 10 秒内未触发"
            for ww in shell.windows():
                try:
                    ww.destroy()
                except Exception:
                    pass

    threading.Timer(1.0, fallback).start()
    shell.start()
    if result.get("loaded"):
        print(f"[smoke] OK — 系统内核 WebView 可用（loaded: {result.get('url')!r}）")
        return 0
    print(f"[smoke] FAIL — {result.get('err') or 'unknown'}")
    return 1


if __name__ == "__main__":
    import threading

    sys.exit(main())

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

import os
import sys
import threading
from typing import Any

from app.api_bridge import SEARCH_ENGINES, START_URL, Api, on_loaded


def _apply_dnt_header(window: Any) -> None:
    """为每个 HTTP 请求注入 DNT: 1 头（落地 A-①）。

    通过 pywebview 的 request_sent 事件（WebView2 WebResourceRequested）
    修改请求头。pywebview 版本不支持该事件/请求头修改时静默降级。
    """
    try:
        events = getattr(window, "events", None)
        if events is None:
            return
        if not hasattr(events, "request_sent"):
            return  # 版本不支持 → 静默降级

        def _on_request(request: Any) -> None:
            try:
                headers = getattr(request, "headers", None)
                if headers is not None:
                    headers["DNT"] = "1"
            except Exception:
                pass  # 单个请求修改失败不影响其他请求

        events.request_sent += _on_request
    except Exception:
        pass  # 事件绑定失败静默，不影响浏览


def _apply_enhanced_security(window: Any, mode: str = "auto") -> None:
    """启用 WebView2 Enhanced Security Mode（落地②，支持三模式决策）。

    背景（2026-08 调研）：微软将 EnhancedSecurityModeLevel 更名为
    EnhancedSecurityModeState（Disabled/Enabled），新 API 为 profile 级
    （COM ICoreWebView2ExperimentalProfile17，Runtime 151+ 可用）。
    pywebview 未封装该 API，但底层 WinForms WebView2 控件可通过
    window.gui.webview.CoreWebView2.Profile 访问。

    策略（对应 config.security_enhanced_mode）：
    - auto（默认）：探测到 EnhancedSecurityModeState 才启用；
    - on：强制启用（无 API 时静默降级，不影响浏览启动）；
    - off：显式跳过（兼容依赖 JIT/WASM 的老站点）。
    per-origin 例外（config.security_esm_exceptions）依赖实验
    Origin Configuration API，探测到才应用；任何失败静默降级。
    """
    try:
        if mode == "off":
            return  # 显式关闭：不启用 ESM
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        profile = getattr(core, "Profile", None)
        if profile is None or not hasattr(profile, "EnhancedSecurityModeState"):
            return  # Runtime 过旧/API 未暴露 → 静默降级
        # Enabled=1（对应枚举 CoreWebView2EnhancedSecurityModeState.Enabled）
        profile.EnhancedSecurityModeState = 1
    except Exception:
        pass  # 启用失败静默，不影响浏览


def main() -> int:
    import webview  # type: ignore[import-not-found]  # pywebview 为运行时依赖，类型桩缺失时忽略

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

    # 落地②：WebView2 兼容性探测（Runtime 版本 + 关键 API 可用性，
    # 写日志供监控/排障；Evergreen 2 周更新节奏下用于回归基线）
    try:
        from app.webview2_probe import (
            build_probe_report,
            compare_baseline,
            probe_performance,
            watch_runtime_update,
        )
        report = build_probe_report(window)
        from crash_reporter import log_event
        log_event(f"[probe] {report}")
        # 落地④：性能基线快照 + 与上次基线对比（内存显著变化告警）
        try:
            tab_count = len(api.get_tabs().get("tabs", []))
            perf = probe_performance(window, tab_count=tab_count)
            log_event(f"[perf] {perf}")
            import json as _json

            from app.paths import resolve_data_dir
            baseline_path = os.path.join(
                resolve_data_dir(), "webview2_perf_baseline.json")
            baseline: dict = {}
            try:
                with open(baseline_path, "r", encoding="utf-8") as f:
                    baseline = _json.load(f) or {}
            except (OSError, ValueError):
                baseline = {}
            diff = compare_baseline(perf, baseline)
            if diff.get("significant") or diff.get("gpu_changed"):
                log_event(f"[perf] 基线差异: {diff}")
            # 更新基线（当前快照作为下次对比基准）
            try:
                with open(baseline_path, "w", encoding="utf-8") as f:
                    _json.dump(perf, f, ensure_ascii=False)
            except OSError:
                pass
        except Exception:
            pass  # 性能监控失败静默，不影响浏览
        # 版本对比监控：Evergreen 后台下载新 Runtime 后，提示采用新版本
        # （持续运行的应用会继续用旧版，有安全影响；监听事件记录日志）
        def _on_new_runtime(ver: str) -> None:
            try:
                log_event(f"[probe] 新 WebView2 Runtime 可用: {ver or 'unknown'}"
                          f"（当前 {report.get('runtime_version', '')}，建议重启采用）")
            except Exception:
                pass
        watch_runtime_update(window, on_new_version=_on_new_runtime)
    except Exception:
        pass  # 探测失败静默，不影响浏览

    # 落地③：WebView2 进程崩溃监听（ProcessFailed.CrashReport，2026-07 新 API）。
    # 渲染/GPU 子进程崩溃时 Python 主进程仍存活，借此把崩溃详情写入
    # crash_reports/events.log（异常码/故障模块/偏移/崩溃 ID）；CrashReport
    # 为 None（正常退出/外部 kill/启动失败/挂起）时仅记录 kind 概要。
    try:
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        if core is not None and hasattr(core, "ProcessFailed"):
            def _on_process_failed(sender=None, args=None) -> None:
                try:
                    from crash_reporter import log_webview2_crash
                    kind = ""
                    report = None
                    if args is not None:
                        kind = str(getattr(args, "ProcessFailedKind", "") or "")
                        report = getattr(args, "CrashReport", None)
                    log_webview2_crash(report, kind=kind)
                except Exception:
                    pass  # 记录失败静默，不影响浏览
            core.ProcessFailed += _on_process_failed
    except Exception:
        pass  # 事件绑定失败静默，不影响浏览

    # 落地②：WebView2 Enhanced Security Mode（Runtime 151+ 可用；
    # 读取 config.security_enhanced_mode：auto=探测启用/on=强制/off=关闭；
    # 尽力而为，API 未暴露/失败时静默降级，不影响浏览）
    try:
        esm_mode = "auto"
        try:
            esm_mode = str(getattr(api.config, "security_enhanced_mode", "auto")
                           or "auto")
            if esm_mode not in ("auto", "on", "off"):
                esm_mode = "auto"
        except Exception:
            esm_mode = "auto"
        _apply_enhanced_security(window, mode=esm_mode)
    except Exception:
        pass  # 启用失败静默，不影响浏览

    # 落地 A-①：隐私影子字段新栈接入 — DNT 请求头。
    # config.do_not_track=True 时通过 pywebview request_sent 事件为
    # 每个 HTTP 请求注入 DNT: 1 头（底层 WebView2 WebResourceRequested）。
    # pywebview 版本不支持该事件时静默降级，不影响浏览。
    try:
        from app.config import AppConfig
        dnt_enabled = True  # 默认开启（与 config 默认值一致）
        if api.config is not None:
            dnt_enabled = bool(getattr(api.config, "do_not_track", True))
        if dnt_enabled:
            _apply_dnt_header(window)
    except Exception:
        pass  # DNT 注入失败静默，不影响浏览

    # S5：Windows 11 系统级亚克力/Mica 背景（尽力而为，失败静默降级到 CSS 毛玻璃）
    try:
        from app.backdrop import apply_system_backdrop
        apply_system_backdrop(window, material="mica")
    except Exception:
        pass  # 非 Win11 / DWM 不可用等情形下静默，不影响浏览

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
    import threading

    sys.exit(main())

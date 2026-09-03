"""native_monitoring.py —— WebView2 探测监控与崩溃监听（单文件单职责）。

P0-1 修复（全面审计 2026-09-04）随迁自 main_webview.py：能力探测/性能
基线/Runtime 更新监听/周期复采样 + ProcessFailed 崩溃留痕。解析统一走
shell_adapter.resolve_core 单源；绑定失败显式留痕。
"""

from __future__ import annotations

import os
from typing import Any

from app.shell_adapter import (
    resolve_core as _resolve_core,
)
def _install_probe_and_monitoring(window, api):
    """WebView2 探测/性能基线/Runtime 监控/24h 复采样（547-610 段迁移）。"""
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
        # 方向④-P2：24h 周期性能复采样（慢速内存泄漏趋势；守护线程，
        # 复用 compare_baseline，显著变化/GPU 切换写日志）
        try:
            from app.paths import resolve_data_dir
            from app.webview2_probe import start_periodic_sampling
            start_periodic_sampling(
                window,
                tab_count_fn=lambda: len(api.get_tabs().get("tabs", [])),
                interval_hours=24.0,
                baseline_path=os.path.join(
                    resolve_data_dir(), "webview2_perf_baseline.json"),
            )
        except Exception:
            pass  # 复采样启动失败静默，不影响浏览
    except Exception:
        pass  # 探测失败静默，不影响浏览


def _install_crash_listener(window, core: Any = None):
    """WebView2 进程崩溃监听（落地③：ProcessFailed.CrashReport）。

    渲染/GPU 子进程崩溃时 Python 主进程仍存活，借此把崩溃详情写入
    crash_reports/events.log（异常码/故障模块/偏移/崩溃 ID）。
    P0-1 修复（全面审计 2026-09-04）：解析改走单源 _resolve_core；
    绑定失败显式留痕（崩溃可观测性缺失必须可见）。
    """
    from crash_reporter import log_event
    try:
        if core is None:
            core = _resolve_core(window)
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
            log_event("[native] WebView2 进程崩溃监听已注册")
        else:
            log_event("[native] 崩溃监听未注册：ProcessFailed API 不可用"
                      "（核心未就绪或 Runtime 过旧）")
    except Exception as exc:
        log_event(f"[native] 崩溃监听绑定失败: {exc!r}")

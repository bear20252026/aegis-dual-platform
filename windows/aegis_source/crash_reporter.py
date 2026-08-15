"""crash_reporter.py —— 崩溃报告收集器（后台静默运行）。

功能：
1. 安装全局异常钩子：sys.excepthook（主线程）+ threading.excepthook（后台线程）
2. 任何线程未捕获异常 → 立即 dump 所有线程栈 + 异常详情 → 写入报告文件
3. 报告文件：<data_dir>/crash_reports/crash_YYYYmmdd_HHMMSS_<pid>.log
4. 同时保留一份 crash_reports/latest.log 便于快速查看
5. 静默设计：绝不弹窗、绝不阻塞主流程 —— 只写文件

用法：
    from crash_reporter import install_crash_reporter
    install_crash_reporter(data_dir)

报告内容：时间戳 / 版本 / 平台 / 异常类型与消息 / 完整 traceback /
全部线程栈（faulthandler.dump_traceback）——足以定位死锁与崩溃点。
"""

from __future__ import annotations

import faulthandler
import os
import platform
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

_APP_VERSION = "2.1.6"


def _resolve_app_version() -> str:
    """从 shared/version.properties 读取版本（单一来源，审计 E 修复）。

    读取失败时回退内置固定值（崩溃报告必须永不失效）。
    仅用于崩溃报告元信息，不影响任何功能。
    """
    try:
        root = Path(__file__).resolve().parent.parent.parent
        props = root / "shared" / "version.properties"
        for line in props.read_text(encoding="utf-8").splitlines():
            if line.startswith("VERSION_NAME="):
                v = line.split("=", 1)[1].strip()
                if v:
                    return v
    except Exception:
        pass
    return _APP_VERSION


_APP_VERSION = _resolve_app_version()
_report_cache: Path | None = None
_installed = False


def _report_dir() -> Path | None:
    global _report_cache
    if _report_cache is not None:
        return _report_cache
    # 默认数据目录：源码运行用工程根，打包后 exe 旁
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    _report_cache = base / "crash_reports"
    try:
        _report_cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        _report_cache = None
    return _report_cache


def _thread_stacks() -> str:
    """收集所有线程的栈（不含当前线程自身）。"""
    out: list[str] = []
    current_id = threading.current_thread().ident
    for tid, frame in sys._current_frames().items():
        if tid == current_id:
            continue
        out.append(f"--- thread {tid} (id={tid}) ---")
        out.extend(traceback.format_stack(frame))
    return "\n".join(out) if out else "(无其他线程栈)"


def _write_report(kind: str, exc_text: str) -> str:
    """写崩溃报告文件，返回文件路径。"""
    d = _report_dir()
    if d is None:
        return ""
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = d / f"crash_{ts}_{os.getpid()}.log"
    lines = [
        "=" * 72,
        f"Aegis 崩溃报告  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"版本: {_APP_VERSION}  平台: {platform.platform()}",
        f"Python: {platform.python_version()}  架构: {platform.machine()}",
        f"类型: {kind}",
        "=" * 72,
        "",
        exc_text,
        "",
        "----- 全部线程栈 -----",
        _thread_stacks(),
        "",
        "=" * 72,
        "报告结束",
        "",
    ]
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
        # 同步最新报告
        try:
            (d / "latest.log").write_text("\n".join(lines), encoding="utf-8")
        except OSError:
            pass
        # W-07 整改（国防级审查）：日志文件平台权限收紧（目录 ACL——
        # POSIX 0600 / Windows DACL——security.harden_perms）
        try:
            from app.security import harden_perms
            harden_perms(str(path))
        except Exception:
            pass
    except OSError:
        return ""
    return str(path)


def _handle(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
    """统一处理未捕获异常：写报告，不弹窗。"""
    if issubclass(exc_type, KeyboardInterrupt):
        return  # 用户主动中断不算崩溃
    exc_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    path = _write_report(f"uncaught:{exc_type.__name__}", exc_text)
    # 报告路径打进 stderr，便于开发者从控制台看到
    try:
        print(f"[crash] 已记录崩溃报告: {path}", file=sys.stderr)
    except Exception:
        pass


def _handle_thread(args: Any) -> None:
    """后台线程未捕获异常处理（threading.excepthook）。"""
    exc_text = "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    path = _write_report(f"thread:{args.exc_type.__name__}", exc_text)
    try:
        print(f"[crash] 后台线程异常，已记录: {path}", file=sys.stderr)
    except Exception:
        pass


def install_crash_reporter(data_dir: str | None = None) -> None:
    """安装崩溃报告收集器。可重复调用（幂等）。

    :param data_dir: 报告存放根目录（crash_reports 子目录）。None = 自动探测。
    """
    global _report_cache, _installed
    if _installed:
        return
    if data_dir:
        try:
            _report_cache = Path(data_dir) / "crash_reports"
            _report_cache.mkdir(parents=True, exist_ok=True)
        except OSError:
            _report_cache = None
    # 主线程未捕获异常
    sys.excepthook = _handle
    # 后台线程未捕获异常
    threading.excepthook = _handle_thread
    # 崩溃信号（segfault 等）也尽力留痕
    try:
        faulthandler.enable()
    except Exception:
        pass
    _installed = True


def log_event(msg: str) -> None:
    """主动记录一条运行事件（非崩溃，供排查）。追加到 events.log。"""
    # 内存凭据不落地（KNOWLEDGE_BASE 第 14 节借鉴 FreeDom 反 dump）：
    # 日志写入前经 credential_guard 脱敏凭据值（防御式，不改变功能）
    try:
        from app.credential_guard import redact
        msg = redact(msg)
    except Exception:
        pass  # 脱敏失败保持原样，不影响日志
    d = _report_dir()
    if d is None:
        return
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
        with open(d / "events.log", "a", encoding="utf-8") as f:
            f.write(line)
        # W-07 整改（国防级审查）：事件日志文件权限收紧（目录 ACL——
        # POSIX 0600 / Windows DACL——security.harden_perms）
        try:
            from app.security import harden_perms
            harden_perms(str(d / "events.log"))
        except Exception:
            pass
    except OSError:
        pass


def log_webview2_crash(crash_report: Any, kind: str = "") -> None:
    """记录 WebView2 进程崩溃报告（落地③，ProcessFailed.CrashReport）。

    2026-07 起 WebView2 SDK 1.0.4126 在 ProcessFailed 事件提供 CrashReport
    （异常码/故障模块/故障偏移/崩溃 ID/bucket ID/报告时间）。渲染进程崩溃
    时 Python 主进程仍存活，此函数把崩溃详情记入 events.log 供定位。

    判空约定（微软）：CrashReport 为 None 表示非崩溃失败（正常退出/
    外部 kill/启动失败/挂起），此时仅记录 ProcessFailedKind 概要。
    """
    if crash_report is None:
        log_event(f"[webview2] 进程失败（无崩溃报告） kind={kind or 'unknown'}")
        return
    try:
        fields = {
            "code": getattr(crash_report, "ExceptionCode", None),
            "module": getattr(crash_report, "FaultingModuleName", None),
            "module_ver": getattr(crash_report, "FaultingModuleVersion", None),
            "offset": getattr(crash_report, "FaultOffset", None),
            "crash_id": getattr(crash_report, "CrashReportId", None),
            "bucket": getattr(crash_report, "BucketId", None),
            "time": getattr(crash_report, "ReportTime", None),
        }
        parts = [f"{k}={v}" for k, v in fields.items() if v is not None]
        log_event(f"[webview2] 崩溃报告 kind={kind or 'unknown'} "
                  + " ".join(parts))
    except Exception:
        pass  # 提取失败静默（崩溃报告是诊断增强，不影响浏览）


# ============================================================================
# 看门狗（Watchdog）：检测"挂起/死锁" —— 异常收集器抓不到的死锁场景
# ============================================================================
_watchdogs: list[tuple[threading.Event, threading.Thread]] = []


def dump_threads_to_report(reason: str) -> str:
    """主动把当前全部线程栈写入崩溃报告（用于死锁/挂起检测）。"""
    exc_text = f"[watchdog] {reason}\n"
    path = _write_report(f"watchdog:{reason[:40]}", exc_text)
    return path


def start_watchdog(check_fn, interval: float = 3.0, timeout: float = 8.0,
                   name: str = "watchdog") -> None:
    """启动一个看门狗线程。

    :param check_fn: 无参调用，返回 True 表示健康；返回 False 表示疑似挂起
    :param interval: 检查间隔（秒）
    :param timeout: 连续不健康多少次判定为死锁（× interval ≈ 判定时长）
    :param name: 看门狗名称（写进报告）
    """
    stop = threading.Event()

    def _loop() -> None:
        bad = 0
        while not stop.is_set():
            stop.wait(interval)
            if stop.is_set():
                break
            try:
                ok = bool(check_fn())
            except Exception:
                ok = False
            if ok:
                bad = 0
                continue
            bad += 1
            if bad * interval >= timeout:
                path = dump_threads_to_report(f"{name} 疑似挂起（连续 {bad} 次不健康）")
                try:
                    print(f"[watchdog] {name} 疑似挂起，报告: {path}", file=sys.stderr)
                except Exception:
                    pass
                bad = 0  # 避免刷屏：写一次报告后重置

    t = threading.Thread(target=_loop, name=f"aegis-{name}", daemon=True)
    t.start()
    _watchdogs.append((stop, t))


def stop_watchdogs() -> None:
    for stop, _t in _watchdogs:
        stop.set()

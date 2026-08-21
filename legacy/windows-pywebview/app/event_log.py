"""event_log.py —— 统一日志接口（单文件单职责：业务层日志入口）。

背景（2026-08-15，代码质量改进点：可复用性）：业务层（api_bridge/
nav_queue/webview2_probe）此前 5 处重复"延迟导入 crash_reporter +
try 包裹"调用日志——本模块统一该入口，业务层仅依赖 app 内接口，
crash_reporter（顶层基础设施）只在内部委托（分层契约允许：
crash_reporter 为可被所有层依赖的基础设施层）。

行为：与 crash_reporter.log_event 完全一致（含 credential_guard
凭据脱敏——log_event 内部已接入）；失败静默（日志失败不影响业务）。
"""

from typing import Any


def log_event(msg: Any) -> None:
    """记录一条运行事件（委托 crash_reporter.log_event；失败静默）。

    统一入口：业务层调用本函数即获得崩溃报告器日志 + 凭据脱敏
    （credential_guard.redact 已在 crash_reporter.log_event 内部接入），
    无需重复延迟导入/异常包裹。
    """
    try:
        from crash_reporter import log_event as _log
        _log(msg)
    except Exception:
        pass  # 日志失败静默（与历史行为一致，不影响业务）

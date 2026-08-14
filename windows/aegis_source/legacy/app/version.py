# -*- coding: utf-8 -*-
"""version.py —— 应用版本与语义化比较（更新器依赖）。

诚实原则：APP_VERSION 为本浏览器自身版本；引擎版本（Chromium）由
QtWebEngine 运行时决定，绝不硬编码虚构的大版本号。引擎版本通过
engine_version() 在运行时如实读取。
"""

APP_NAME = "Aegis"
APP_VERSION = "2.1.6"


def parse_semver(text: str):
    """把 '1.2.3' / 'v1.2.3-beta' 解析为可比较元组 (1,2,3)。解析失败返回 (0,0,0)。"""
    try:
        core = text.strip().lstrip("vV").split("-")[0].split("+")[0]
        parts = [int(p) for p in core.split(".") if p.strip().isdigit()]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except (AttributeError, ValueError):
        return (0, 0, 0)


def is_newer(remote: str, current: str = APP_VERSION) -> bool:
    """remote 版本是否比 current 新。"""
    return parse_semver(remote) > parse_semver(current)


def pyside_version() -> str:
    """如实返回 PySide6 版本（无则为未知）。"""
    try:
        import PySide6
        return PySide6.__version__
    except Exception:
        return "unknown"


def engine_version() -> str:
    """如实返回底层引擎信息：PySide6 + QtWebEngine 捆绑的 Chromium。

    不臆造版本号；Chromium 具体版本由 Qt 运行时提供，
    读取失败时如实回退到 PySide6 版本。
    """
    pv = pyside_version()
    try:
        from PySide6.QtWebEngineCore import qWebEngineVersion
        ce = qWebEngineVersion()
        if ce:
            return f"QtWebEngine {ce} (PySide6 {pv})"
    except Exception:
        pass
    return f"PySide6 {pv} (Chromium 版本由运行时决定)"


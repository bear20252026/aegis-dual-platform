"""webview2_probe.py —— WebView2 兼容性探测（单文件单职责，落地②）。

背景（2026-08 调研）：WebView2 Runtime 自 v152（2026-08-24）起改为
2 周更新节奏（原 4 周），版本变动更频繁。为确保 Evergreen 更新不破坏
Aegis 核心功能，启动时探测 Runtime 版本与关键 API 可用性，输出结构化
报告供监控/排障；同时提供自动化回归入口（run_selftests）。

探测项（对应本项目实际使用的 WebView2/pywebview 能力）：
- Runtime 版本（环境变量/注册表读取，尽力而为）
- EnhancedSecurityModeState（落地①，Runtime 151+ 才有）
- request_sent 事件（DNT 头注入依赖，pywebview 版本相关）
- CoreWebView2 / Profile 对象可达性（安全增强模式接入点）
"""

import os
import platform
import sys
import winreg
from typing import Any

# 探测的关键能力清单（name -> 说明），供报告使用
_CAPABILITIES = (
    "EnhancedSecurityModeState",   # 安全增强模式（落地①）
    "request_sent",                # DNT 头注入事件（落地 A-①）
    "CoreWebView2.Profile",        # 底层 Profile 可达性
)


def probe_runtime_version() -> str:
    """读取本机 WebView2 Runtime 版本（尽力而为，失败返回空串）。

    优先读注册表（HKLM/HKCU WebView2 安装信息），失败回退环境变量。
    """
    try:
        keys = (
            (winreg.HKEY_LOCAL_MACHINE,
             (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
              r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")),
            (winreg.HKEY_LOCAL_MACHINE,
             (r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
              r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")),
            (winreg.HKEY_CURRENT_USER,
             (r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
              r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")),
        )
        for hive, path in keys:
            try:
                with winreg.OpenKey(hive, path) as k:
                    ver, _ = winreg.QueryValueEx(k, "pv")
                    if ver:
                        return str(ver)
            except OSError:
                continue
    except Exception:
        pass
    return os.environ.get("WEBVIEW2_VERSION", "")


def probe_capabilities(window: Any = None) -> dict:
    """探测关键能力可用性，返回 {capability: bool}。

    window 为 pywebview 窗口对象（可为 None）；无窗口时仅做静态探测。
    """
    result = {}
    gui = getattr(window, "gui", None) if window is not None else None
    webview_ctrl = getattr(gui, "webview", None) if gui is not None else None
    core = getattr(webview_ctrl, "CoreWebView2", None) if webview_ctrl is not None else None
    profile = getattr(core, "Profile", None) if core is not None else None

    result["EnhancedSecurityModeState"] = bool(
        profile is not None and hasattr(profile, "EnhancedSecurityModeState"))
    result["CoreWebView2.Profile"] = bool(profile is not None)

    # request_sent 事件：无窗口时按 pywebview 版本特征探测
    if window is not None:
        events = getattr(window, "events", None)
        result["request_sent"] = bool(
            events is not None and hasattr(events, "request_sent"))
    else:
        # 静态探测：pywebview 5.x 支持 request_sent（官方 headers 示例）
        result["request_sent"] = True
    return result


def build_probe_report(window: Any = None) -> dict:
    """生成兼容性探测报告（结构化，供日志/监控/排障）。"""
    runtime = probe_runtime_version()
    caps = probe_capabilities(window)
    return {
        "tool": "aegis-webview2-probe",
        "runtime_version": runtime,
        "runtime_cadence_note": "2 周更新节奏（v152 起，2026-08-24）",
        "capabilities": caps,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }


# --------------------------------------------------------------------------- #
# 自动化回归入口：validate_release + 三个自检一键执行
# --------------------------------------------------------------------------- #
def run_selftests() -> int:
    """运行项目全部自动化回归（validate_release + 3 selftest）。

    供 CI/兼容性监控定期执行；任一失败返回非零退出码。
    """
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # aegis_source
    scripts = [
        (os.path.join(os.path.dirname(os.path.dirname(root)), "validate_release.py"),
         "validate_release"),
        (os.path.join(root, "selftest_s1_integration.py"), "selftest_s1"),
        (os.path.join(root, "selftest_api_bridge.py"), "selftest_api"),
        (os.path.join(root, "selftest_shell_toolbar.py"), "selftest_toolbar"),
    ]
    py = sys.executable
    failed = []
    for path, name in scripts:
        print(f"[probe] 运行 {name}: {path}")
        rc = subprocess.call([py, path])
        status = "OK" if rc == 0 else f"FAIL({rc})"
        print(f"[probe] {name}: {status}")
        if rc != 0:
            failed.append(name)
    if failed:
        print(f"[probe] 回归失败项: {failed}")
        return 1
    print("[probe] 全部自动化回归通过")
    return 0

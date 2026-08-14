# -*- coding: utf-8 -*-
"""system_theme.py —— 操作系统深浅色检测（主题"跟随系统"）。

Windows：注册表 AppsUseLightTheme；macOS：defaults；Linux：GTK 主题名嗅探。
任何分支失败都安全回退为深色（与默认配置一致）。
"""

import sys
import time

_cache = {"ts": 0.0, "dark": True}   # 60s 缓存，避免频繁读注册表/起子进程


def system_is_dark() -> bool:
    now = time.time()
    if now - _cache["ts"] < 60:
        return _cache["dark"]
    dark = _detect()
    _cache["ts"], _cache["dark"] = now, dark
    return dark


def resolve_dark(theme: str) -> bool:
    """把配置主题（auto/dark/light）解析为当前实际深色布尔值。"""
    if theme == "light":
        return False
    if theme == "dark":
        return True
    return system_is_dark()


def _detect() -> bool:
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            try:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(value) == 0
            finally:
                winreg.CloseKey(key)
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2)
            return "dark" in (out.stdout or "").lower()
        else:
            import os
            gtk = (os.environ.get("GTK_THEME", "") +
                   os.environ.get("QT_STYLE_OVERRIDE", "")).lower()
            if gtk:
                return "dark" in gtk
            # GNOME gsettings 查询（可能不存在）
            import subprocess
            try:
                out = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface",
                     "color-scheme"],
                    capture_output=True, text=True, timeout=2)
                return "dark" in (out.stdout or "").lower()
            except Exception:
                pass
    except Exception:
        pass
    return True

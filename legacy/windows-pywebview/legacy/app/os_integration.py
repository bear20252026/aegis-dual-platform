"""os_integration.py —— 操作系统深度集成（标准 #35）。

- Windows 任务栏分组：设置 AppUserModelID
- 注册 aegis:// 协议（写入 HKCU，无需管理员，可随时注销）
- "设为默认浏览器"指引（写 HKCU 的 http/https 关联）

所有注册表操作均限定在当前用户键（HKCU），失败静默降级。
"""

import sys

PROTOCOL = "aegis"


def set_app_user_model_id(app_id: str = "Aegis.Aegis.1"):
    """Windows 任务栏图标分组/通知归属。非 Windows 无操作。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    return f'"{sys.executable}" "{_main_py()}" "%1"'


def _main_py() -> str:
    import os
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "main.py")


def register_protocol() -> bool:
    """注册 aegis:// 协议到 HKCU（True=成功）。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        root = winreg.HKEY_CURRENT_USER
        base = rf"Software\Classes\{PROTOCOL}"
        with winreg.CreateKey(root, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Aegis Protocol")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(root, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _exe_path())
        return True
    except Exception:
        return False


def unregister_protocol():
    if sys.platform != "win32":
        return
    try:
        import winreg
        _delete_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROTOCOL}")
    except Exception:
        pass


def _delete_tree(root, path: str):
    import winreg
    try:
        with winreg.OpenKey(root, path, 0,
                            winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(k, sub)
        winreg.DeleteKey(root, path)
    except OSError:
        pass


def set_default_browser() -> bool:
    """把 http/https 关联到本程序（HKCU 层，用户可随时在系统设置中改回）。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        root = winreg.HKEY_CURRENT_USER
        prog = "AegisURL"
        base = rf"Software\Classes\{prog}"
        with winreg.CreateKey(root, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Aegis HTML Document")
        with winreg.CreateKey(root, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _exe_path())
        for scheme in ("http", "https"):
            with winreg.CreateKey(
                    root,
                    rf"Software\Microsoft\Windows\Shell\Associations"
                    rf"\UrlAssociations\{scheme}\UserChoice") as k:
                winreg.SetValueEx(k, "ProgId", 0, winreg.REG_SZ, prog)
        return True
    except Exception:
        return False

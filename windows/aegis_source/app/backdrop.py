"""backdrop.py —— Windows 系统级亚克力/Mica 背景（单文件单职责）。

职责：在 Windows 11 上为浏览器主窗口启用系统级背景材质（Mica /
Acrylic），让窗口背景呈现毛玻璃效果 —— 比 CSS backdrop-filter 更贴近
苹果风格（原生 DWM 材质，含窗口圆角与系统级模糊）。

设计原则（S5）：
- **尽力而为（best-effort）**：依赖 DWM API（dwmapi.dll）与 Win11
  版本号；任何一步失败（非 Win11 / 无窗口句柄 / API 不可用）都静默
  返回 False，绝不抛异常 —— 浏览器功能不受影响。
- **静默降级**：失败时保留 shell_toolbar.py 中已有的 CSS
  backdrop-filter 毛玻璃工具栏，外观仍然可用。
- 通过 ctypes 直接调用（不引入 pywin32 等额外依赖）。
"""

import ctypes
import sys

# DWMWA_SYSTEMBACKDROP_TYPE：Win11 22621+ 的 DWM 属性
_DWMWA_SYSTEMBACKDROP_TYPE = 38
# 材质类型：Mica = 2，Acrylic = 3
_DWMSBT_MAINWINDOW = 2   # Mica
_DWMSBT_TRANSIENTWINDOW = 3  # Acrylic

# Win11 最低 build：22621（22H2）
_WIN11_MIN_BUILD = 22621


def _win11_or_newer() -> bool:
    """检查当前 Windows 版本是否 >= Win11 22H2（支持系统背景材质）。"""
    try:
        if sys.platform != "win32":
            return False
        # RtlGetVersion 获取真实版本（GetVersionEx 受 manifest 影响不可靠）
        class OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [
                ("dwOSVersionInfoSize", ctypes.c_ulong),
                ("dwMajorVersion", ctypes.c_ulong),
                ("dwMinorVersion", ctypes.c_ulong),
                ("dwBuildNumber", ctypes.c_ulong),
                ("dwPlatformId", ctypes.c_ulong),
                ("szCSDVersion", ctypes.c_wchar * 128),
            ]
        ver = OSVERSIONINFOEXW()
        ver.dwOSVersionInfoSize = ctypes.sizeof(OSVERSIONINFOEXW)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        if ntdll.RtlGetVersion(ctypes.byref(ver)) != 0:
            return False
        return ver.dwBuildNumber >= _WIN11_MIN_BUILD
    except Exception:
        return False


def apply_system_backdrop(window, material: str = "mica") -> bool:
    """为 pywebview 窗口启用系统背景材质。

    :param window: pywebview 的 Window 对象（create_window 返回）
    :param material: "mica"（默认）或 "acrylic"
    :return: 是否成功应用（失败静默返回 False，不影响主流程）
    """
    if not _win11_or_newer():
        return False
    try:
        native = getattr(window, "native", None)
        if native is None:
            return False
        # winforms 后端：native 是 System.Windows.Forms.Form，取句柄
        handle = getattr(native, "Handle", None) or getattr(native, "hwnd", None)
        if not handle:
            return False
        hwnd = int(handle)
        value = _DWMSBT_MAINWINDOW if material == "mica" else _DWMSBT_TRANSIENTWINDOW
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            _DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(ctypes.c_int(value)),
            ctypes.sizeof(ctypes.c_int),
        )
        return result == 0  # S_OK
    except Exception:
        return False

"""Windows 发布容器检测。

MSIX/App Installer 负责包更新、修复和卸载；应用内 EXE 下载更新器不得在
MSIX 环境中并行运行，避免两个更新器争夺版本与安装目录。
"""
from __future__ import annotations

import ctypes
import os
import sys


def is_msix_packaged() -> bool:
    """返回当前 Windows 进程是否运行在具有 Package Identity 的容器中。"""
    if os.environ.get("AEGIS_FORCE_MSIX", "").strip() == "1":
        return True
    if sys.platform != "win32":
        return False
    try:
        # GetCurrentPackageFamilyName: APPMODEL_ERROR_NO_PACKAGE 表示传统进程。
        length = ctypes.c_uint32(0)
        status = ctypes.windll.kernel32.GetCurrentPackageFamilyName(
            ctypes.byref(length), None
        )
        return status == 122  # ERROR_INSUFFICIENT_BUFFER，说明存在 package family
    except Exception:
        return False


def update_owner() -> str:
    """返回当前版本更新的唯一责任方。"""
    return "app-installer" if is_msix_packaged() else "legacy-updater"

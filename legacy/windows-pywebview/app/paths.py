"""paths.py —— 用户数据目录与路径规划。

所有用户数据（配置、数据库、缓存、会话）均隔离在该目录下，
不依赖也不读取 Edge / Chrome 的任何数据。
"""

import os
import sys
import tempfile

APP_NAME = "Aegis"
# MSIX/Windows 默认写入 LocalAppData；开发运行可用 AEGIS_DATA_DIR 覆盖。
DEFAULT_DATA_DIR_NAME = "AegisData"
PACKAGE_DATA_SUBDIR = os.path.join("Aegis", "WebView", "LocalState")


def app_base_dir() -> str:
    """程序所在目录（兼容源码运行与 PyInstaller 打包两种形态）。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后为 exe 所在目录
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_data_dir(explicit: str | None = None) -> str:
    """解析用户数据目录；绝不默认写入 MSIX 安装目录。"""
    explicit = explicit or os.environ.get("AEGIS_DATA_DIR")
    if explicit:
        os.makedirs(explicit, exist_ok=True)
        return os.path.abspath(explicit)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = os.path.join(local_app_data, PACKAGE_DATA_SUBDIR)
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share", APP_NAME)
    os.makedirs(base, exist_ok=True)
    return base


def ensure_dir(path: str) -> str:
    """确保目录存在并返回。"""
    os.makedirs(path, exist_ok=True)
    return path


def profile_dir(base: str, profile_name: str = "default") -> str:
    """返回某个配置文件的根目录（名称已净化），并确保存在。"""
    name = sanitize_profile_name(profile_name)
    return ensure_dir(os.path.join(base, "profiles", name))


def temp_dir() -> str:
    """临时目录：每次调用生成唯一子目录（v1.4 L4 修复，防符号链接竞争）。"""
    base = ensure_dir(os.path.join(tempfile.gettempdir(), APP_NAME))
    return tempfile.mkdtemp(prefix="s-", dir=base)


# 子目录规划
def cache_dir(base: str) -> str:
    return ensure_dir(os.path.join(base, "Cache"))


def webengine_dir(base: str) -> str:
    return ensure_dir(os.path.join(base, "WebEngine"))


def sanitize_profile_name(name: str) -> str:
    """v1.4 M8 修复：配置文件名白名单（防 ../ 路径穿越）。"""
    import re
    clean = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", str(name or ""))[:64]
    return clean or "default"

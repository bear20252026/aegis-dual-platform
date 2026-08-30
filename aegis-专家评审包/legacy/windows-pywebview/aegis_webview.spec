# -*- mode: python ; coding: utf-8 -*-
"""Aegis WebView 版打包规格（onedir，Windows）。

输出：dist/AegisWebView/Aegis.exe + _internal/

与旧版（QtWebEngine）的区别：
- 不再捆绑 PySide6 / QtWebEngine（体积从 700MB+ 降到 100MB 级）
- 运行时借用 Windows Edge WebView2 Evergreen Runtime
- 保留 app/ 业务模块（书签/历史/数据库等纯 Python 逻辑）
- 正式发布只面向 Windows；macOS 后端不纳入依赖或验收范围
"""
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

PROJECT = SPECPATH

# 离线几何画板（GeoGebra Math Apps Bundle——构建期由 CI 从仓库 Release
# 资产拉取解压到 geogebra/；本地无该目录时跳过——不阻塞常规打包）。
_geogebra_dir = os.path.join(PROJECT, "geogebra")

_datas = [
    # 首页资源单一事实源（ADR-007）：shared/shell（start.html + wallpapers）
    (os.path.join(PROJECT, "..", "..", "shared", "shell"), "shell"),
    (os.path.join(PROJECT, "assets"), "assets"),
    *collect_data_files("webview"),
]
if os.path.isdir(_geogebra_dir):
    _datas.append((_geogebra_dir, "geogebra"))

a = Analysis(
    [os.path.join(PROJECT, "main_webview.py")],
    pathex=[PROJECT],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        *collect_submodules("app"),
        "webview",
        "webview.platforms.winforms",
        "bottle",
        "clr_loader",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc", "doctest", "resource",
        "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick", "PySide6.QtNetwork", "PySide6.QtQml",
        "PySide6.QtQuick",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Aegis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(PROJECT, "assets", "icon.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AegisWebView",
)

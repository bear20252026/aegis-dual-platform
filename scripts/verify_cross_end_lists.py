#!/usr/bin/env python3
"""verify_cross_end_lists.py —— 跨端数据清单一致性校验（A-7，架构审计 2026-08-31）。

壁纸与搜索引擎清单在多端平行维护，历史上无任何一致性校验（扩散系数 4/2）。
本脚本 fail-closed：任一端缺失/多出条目即退出码 1。

覆盖面：
1. 壁纸清单 4 处：
   - shared/shell/wallpapers/ 实际文件
   - legacy/windows-pywebview/app/asset_scheme.py（Windows 资产服务白名单）
   - shared/shell/start.html（UI 按钮列表——单源 UI）
   - android/.../AegisHomeBridge.kt（Android 白名单）
2. 搜索引擎清单 2 处：
   - legacy/windows-pywebview/app/url_utils.py（Windows 引擎表）
   - android/.../AegisHomeBridge.kt ENGINE_URLS
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def wallpapers_from_asset_scheme() -> set[str]:
    text = (ROOT / "legacy/windows-pywebview/app/asset_scheme.py").read_text(encoding="utf-8")
    block = re.search(r"WALLPAPERS\s*=\s*\(([^)]*)\)", text, re.S)
    if not block:
        fail("asset_scheme.py: 未找到 WALLPAPERS 白名单")
        return set()
    return set(re.findall(r'"([^"]+\.jpg)"', block.group(1)))


def wallpapers_from_start_html() -> set[str]:
    text = (ROOT / "shared/shell/start.html").read_text(encoding="utf-8")
    block = re.search(r"var WALLPAPERS\s*=\s*\[(.*?)\];", text, re.S)
    if not block:
        fail("start.html: 未找到 WALLPAPERS 按钮列表")
        return set()
    return set(re.findall(r"name:'([^']+)'", block.group(1)))


def wallpapers_from_kotlin() -> set[str]:
    text = (ROOT / "android/app/src/main/java/com/aegis/browser/AegisHomeBridge.kt").read_text(
        encoding="utf-8"
    )
    block = re.search(r"WALLPAPERS\s*=\s*setOf\((.*?)\)", text, re.S)
    if not block:
        fail("AegisHomeBridge.kt: 未找到 WALLPAPERS 白名单")
        return set()
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def wallpapers_on_disk() -> set[str]:
    d = ROOT / "shared/shell/wallpapers"
    return {p.name for p in d.glob("*.jpg")}


def engines_from_url_utils() -> set[str]:
    text = (ROOT / "legacy/windows-pywebview/app/url_utils.py").read_text(encoding="utf-8")
    block = re.search(r"SEARCH_ENGINES[^=]*=\s*\{(.*?)\n\}", text, re.S)
    if not block:
        fail("url_utils.py: 未找到 SEARCH_ENGINES 表")
        return set()
    return set(re.findall(r'^\s*"([^"]+)"\s*:', block.group(1), re.M))


def engines_from_kotlin() -> set[str]:
    text = (ROOT / "android/app/src/main/java/com/aegis/browser/AegisHomeBridge.kt").read_text(
        encoding="utf-8"
    )
    block = re.search(r"ENGINE_URLS\s*=\s*mapOf\((.*?)\)\s*$", text, re.S | re.M)
    if not block:
        fail("AegisHomeBridge.kt: 未找到 ENGINE_URLS 表")
        return set()
    return set(re.findall(r'"([^"]+)"\s+to\s+"', block.group(1)))


def diff(label: str, a: set[str], b: set[str], hint: str) -> None:
    if a != b:
        for missing in sorted(b - a):
            fail(f"{label}: {hint} 缺少 {missing}")
        for extra in sorted(a - b):
            fail(f"{label}: {hint} 多出 {extra}")


def main() -> int:
    disk = wallpapers_on_disk()
    py_wp = wallpapers_from_asset_scheme()
    html_wp = wallpapers_from_start_html()
    kt_wp = wallpapers_from_kotlin()
    diff("壁纸", disk, py_wp, "asset_scheme.py 相对磁盘文件")
    diff("壁纸", disk, html_wp, "start.html 相对磁盘文件")
    diff("壁纸", disk, kt_wp, "AegisHomeBridge.kt 相对磁盘文件")

    py_eng = engines_from_url_utils()
    kt_eng = engines_from_kotlin()
    diff("搜索引擎", py_eng, kt_eng, "AegisHomeBridge.kt 相对 url_utils.py")

    if failures:
        print("❌ 跨端清单不一致：")
        for f in failures:
            print("  -", f)
        return 1
    print(
        f"✅ 跨端清单一致（壁纸 {len(disk)} 文件 ×3 端；搜索引擎 {len(py_eng)} ×2 端）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

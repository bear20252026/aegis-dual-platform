#!/usr/bin/env python3
"""verify_cross_end_lists.py —— 跨端数据清单一致性校验（A-7，架构审计 2026-08-31）。

壁纸与搜索引擎清单在多端平行维护，历史上无任何一致性校验（扩散系数 4/2）。
本脚本 fail-closed：任一端缺失/多出条目即退出码 1。

覆盖面：
1. 壁纸清单 5 处（WB-011：C# NtpAssets 增列）：
   - shared/shell/wallpapers/ 实际文件
   - legacy/windows-pywebview/app/asset_scheme.py（Windows 资产服务白名单）
   - shared/shell/start.main.js（UI 按钮列表——单源 UI；I83 外置前在 start.html）
   - android/.../AegisHomeBridge.kt（Android 白名单）
   - windows/.../Chrome/Ntp/NtpAssets.cs（C# 正典栈白名单）
2. 搜索引擎清单 3 处（WB-010：C# UrlNormalizer 增列）：
   - legacy/windows-pywebview/app/url_utils.py（Windows 引擎表）
   - android/.../SearchEngines.kt ENGINE_URLS（搜索审计 2026-09-01：
     引擎表自 AegisHomeBridge 迁至 SearchEngines 单源，锚点同步）
   - windows/.../Chrome/UrlNormalizer.cs EngineUrls（C# 正典栈——
     契约口径：三端核心引擎完全一致；C# 扩展引擎须在
     CS_ENGINE_EXTENSIONS 白名单显式登记，防双向静默漂移）
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
    # I83 外置（2026-09-10）：WALLPAPERS 数组随内联脚本外移 start.main.js
    #（start.html 仅静态标记 + CSP——不再承载脚本数据）
    text = (ROOT / "shared/shell/start.main.js").read_text(encoding="utf-8")
    block = re.search(r"var WALLPAPERS\s*=\s*\[(.*?)\];", text, re.S)
    if not block:
        fail("start.main.js: 未找到 WALLPAPERS 按钮列表")
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


def wallpapers_from_csharp() -> set[str]:
    # WB-011（2026-09-24）：C# 正典栈 NtpAssets.Wallpapers 第 5 份壁纸清单
    text = (ROOT / "windows/src/Aegis.Windows.App/Chrome/Ntp/NtpAssets.cs").read_text(
        encoding="utf-8"
    )
    block = re.search(r"Wallpapers\s*=\s*new\[\]\s*\{(.*?)\}", text, re.S)
    if not block:
        fail("NtpAssets.cs: 未找到 Wallpapers 白名单")
        return set()
    return set(re.findall(r'"([^"]+\.jpg)"', block.group(1)))


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
    # 搜索审计 2026-09-01：ENGINE_URLS 迁至 SearchEngines.kt 单源
    # （AegisHomeBridge 改为引用该单源）——锚点同步更新
    text = (ROOT / "android/app/src/main/java/com/aegis/browser/SearchEngines.kt").read_text(
        encoding="utf-8"
    )
    block = re.search(r"ENGINE_URLS[^=]*=\s*mapOf\(\s*(.*?)\)", text, re.S)
    if not block:
        fail("SearchEngines.kt: 未找到 ENGINE_URLS 表")
        return set()
    return set(re.findall(r'"([^"]+)"\s+to\s+"', block.group(1)))


# WB-010（2026-09-24）：C# 正典栈允许在核心引擎之外扩展（正则锚点 =
# UrlNormalizer.EngineUrls 初始化块的 ["key"] = "url" 条目）。
# 扩展引擎在此显式登记——不在名单内的新增/缺失一律 fail-closed，
# 杜绝 C# 端引擎表双向静默漂移。
CS_ENGINE_EXTENSIONS = frozenset({
    "so360", "duckduckgo", "brave", "startpage", "ecosia", "yandex",
})


def engines_from_csharp() -> set[str]:
    text = (ROOT / "windows/src/Aegis.Windows.App/Chrome/UrlNormalizer.cs").read_text(
        encoding="utf-8"
    )
    block = re.search(r"EngineUrls\s*=\s*new Dictionary[^{]*\{(.*?)\n\s*\};", text, re.S)
    if not block:
        fail("UrlNormalizer.cs: 未找到 EngineUrls 表")
        return set()
    return set(re.findall(r'\["([^"]+)"\]\s*=', block.group(1)))


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
    cs_wp = wallpapers_from_csharp()
    diff("壁纸", disk, py_wp, "asset_scheme.py 相对磁盘文件")
    diff("壁纸", disk, html_wp, "start.main.js 相对磁盘文件")
    diff("壁纸", disk, kt_wp, "AegisHomeBridge.kt 相对磁盘文件")
    diff("壁纸", disk, cs_wp, "NtpAssets.cs 相对磁盘文件")

    py_eng = engines_from_url_utils()
    kt_eng = engines_from_kotlin()
    cs_eng = engines_from_csharp()
    diff("搜索引擎", py_eng, kt_eng, "SearchEngines.kt 相对 url_utils.py")
    # WB-010：三端核心引擎 = url_utils ∩ SearchEngines（py/kt 相等时即并集）；
    # C# 端必须完整覆盖核心，扩展部分仅允许 CS_ENGINE_EXTENSIONS 白名单
    core = py_eng | kt_eng
    if cs_eng < core:
        for missing in sorted(core - cs_eng):
            fail(f"搜索引擎: UrlNormalizer.cs 缺少核心引擎 {missing}")
    extras = cs_eng - core
    for extra in sorted(extras - CS_ENGINE_EXTENSIONS):
        fail(f"搜索引擎: UrlNormalizer.cs 扩展引擎 {extra} 未在 CS_ENGINE_EXTENSIONS 登记（防漂移白名单）")
    for ghost in sorted(CS_ENGINE_EXTENSIONS - cs_eng):
        fail(f"搜索引擎: UrlNormalizer.cs 缺少已登记扩展引擎 {ghost}")

    if failures:
        print("❌ 跨端清单不一致：")
        for f in failures:
            print("  -", f)
        return 1
    print(
        f"✅ 跨端清单一致（壁纸 {len(disk)} 文件 ×4 端；搜索引擎核心 {len(core)} ×3 端"
        f" + C# 扩展 {len(extras)}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

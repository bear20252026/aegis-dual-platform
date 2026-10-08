#!/usr/bin/env python3
"""check_package_floors.py —— .NET 锁里的**版本下界**门禁（第八轮 B7 同批）。

补的是 `verify_lock_rids.py` 第 5 条特意让开的那一格——它的 docstring 写着：
「第 5 条特意不校验版本：`SQLitePCLRaw.bundle_e_sqlite3` 目前解析为 2.1.11（NU1903/
GHSA-2m69-gcr7-jv3q 只修了 3/4，R8-DEPS-3 已登记），版本下限要随 B7 的重锁同批加入
才能既到货就常绿」。本文件就是那下半批：重锁把 4/4 补齐的**同一批**里把它钉成门禁，
否则「补钉」只是一次提交，下一次传递依赖被谁改回 2.1.11 时没人变红。

为什么判「下界」而不是「等于最新」：上游会持续出新版，钉死等值必然周期性红，
而红的原因不是问题——这种门禁的宿命是被「顺手放宽」。下界表达的是安全/契约事实：
2.1.11 命中 GHSA-2m69-gcr7-jv3q；WebView2 低于 csproj 现用版本意味着代码里反射探测
过的那些成员面（`WebView2Hardening.cs:34` 的 ESM、`DownloadItem.cs:101` 的扁平
Progress API）重新变得不可用。

判据三条，每条都可失败：
1. 扫描面非空（复用 `verify_lock_rids.list_lock_files`，不另立口径）——0 份锁 ⇒ exit 2；
2. 下界表非空，且表里每个包名**至少在一把锁里出现过**——包名写错/被改名 ⇒ 判红
   （否则门禁退化成「查了个不存在的对象」的恒绿）；
3. 每把锁、每个依赖图里命中的包，`resolved` 都 ≥ 下界。

退出码：0 通过 / 1 违规 / 2 环境错误（无锁文件或下界表为空）。
用法：`python scripts/check_package_floors.py`（仓库根运行）；`--print` 报告逐项判定。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# 扫描面单源：复用同一份锁清单，不另立口径。直接以脚本方式运行时 sys.path[0] 就是
# scripts/，不需要再手动 insert（那行会立刻被 ruff 的 RUF100 判成「多余 noqa」）。
import verify_lock_rids as vlr

# 版本下界（安全/契约事实，不是「当前最新版」）。值形如 "2.1.12"。
FLOORS = {
    # NU1903 / GHSA-2m69-gcr7-jv3q：2.1.11 及以前命中，2.1.12 起修复。
    "SQLitePCLRaw.bundle_e_sqlite3": "2.1.12",
    "SQLitePCLRaw.core": "2.1.12",
    "SQLitePCLRaw.provider.e_sqlite3": "2.1.12",
    "SQLitePCLRaw.lib.e_sqlite3": "2.1.12",
    # 代码按这版 SDK 的实测成员面写（ESM 反射探测、下载 SuggestedFileName 缺失的
    # 兼容分支）——往下降等于把那些分支变成死代码还自以为在用。
    "Microsoft.Web.WebView2": "1.0.2903.40",
}


def parse_version(text: str) -> tuple[int, ...]:
    """取点分数字段；非数字尾段（预发布/元数据）截断——下界只判数值段。"""
    parts: list[int] = []
    for chunk in text.strip().split("-")[0].split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    return tuple(parts) or (0,)


def at_least(actual: str, floor: str) -> bool:
    """逐段比较，短的一侧补 0（"2.1" 与 "2.1.0" 同版本）。"""
    left, right = parse_version(actual), parse_version(floor)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left >= right


def resolved_versions(lock_path: Path, package: str) -> list[str]:
    """一把锁的**所有**依赖图里该包名的 resolved 值（重复出现即多条，不折叠）。"""
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    found: list[str] = []
    for graph in (data.get("dependencies") or {}).values():
        entry = graph.get(package)
        if isinstance(entry, dict) and entry.get("resolved"):
            found.append(str(entry["resolved"]))
    return found


def violations(locks: list[Path], floors: dict[str, str]) -> list[str]:
    problems: list[str] = []
    seen_packages: set[str] = set()
    for lock in locks:
        for package, floor in floors.items():
            versions = resolved_versions(lock, package)
            if versions:
                seen_packages.add(package)
            for version in versions:
                if not at_least(version, floor):
                    problems.append(
                        f"{vlr.display_rel(lock)}: {package} resolved={version} "
                        f"低于下界 {floor}")
    # 第 2 条：表里写了却一把锁都没命中的包名＝门禁在查不存在的对象
    silent = sorted(set(floors) - seen_packages)
    for package in silent:
        problems.append(f"下界表里的 {package} 在任何一把锁中都没出现——判据已失效")
    return problems


def run(locks: list[Path] | None = None, floors: dict[str, str] | None = None) -> int:
    targets = vlr.list_lock_files() if locks is None else locks
    table = FLOORS if floors is None else floors
    if not targets:
        print("❌ 未找到任何 packages.lock.json（扫描面 windows/**/packages.lock.json）——"
              "在错误目录运行即此形态，判环境错误而不是通过")
        return 2
    if not table:
        print("❌ 版本下界表为空——门禁已空心化")
        return 2
    problems = violations(targets, table)
    if problems:
        for problem in problems:
            print(f"  ❌ {problem}")
        print(f"❌ 版本下界门禁失败（{len(problems)} 项）")
        return 1
    print(f"✅ 版本下界门禁通过（{len(targets)} 把锁、{len(table)} 条下界）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 .NET 锁里的包版本下界")
    parser.add_argument("--print", dest="show", action="store_true",
                        help="逐锁逐包打印判定明细")
    args = parser.parse_args(argv)
    if args.show:
        for lock in vlr.list_lock_files():
            for package, floor in FLOORS.items():
                print(f"{lock.name} {package} -> {resolved_versions(lock, package)} "
                      f"(floor {floor})")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

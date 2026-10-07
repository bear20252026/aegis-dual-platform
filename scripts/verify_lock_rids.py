#!/usr/bin/env python3
"""verify_lock_rids.py —— .NET `packages.lock.json` 的 **RID 块**门禁（第八轮 B7 前置）。

为什么需要它（不是洁癖，是本仓踩过两次的事故形态）：`dotnet build/test -r win-x64
-p:RestoreLockedMode=true` 在锁与 csproj 不一致时，会把 `net10.0-windows7.0/win-x64`
这**一整块**删掉——只删不增，`git diff` 看着像「38 行删除 0 新增」的空白改动，一次审计
会话里差点被提交出去；六个 LockedMode 门禁随后全报 NU1004。更坏的一种是删掉之后有人
「顺手 restore 一下」，锁就静默变成无 RID 形态，出货制品的依赖解析脱离钉版，还**没人变红**。

锁格式（NuGet lock v1，按实树核对，不凭记忆）：`dependencies` 下每个键是一个目标框架
图，值**直接**是「包名 → {type, resolved, contentHash}」的映射——没有 `packages` 这层包装。
RID 图（`<tfm>/<rid>`）只列**按 RID 解析**的包，本仓实测是两件带原生资产的
（`Microsoft.Web.WebView2`、`SQLitePCLRaw.lib.e_sqlite3`），这才是本门禁的判据基础。

判据五条，每条都可失败（少任何一条就退化成「文件能 JSON 解析」的安慰剂）：

1. 每份锁 `version == 1` 且 `dependencies` 是非空对象；
2. 每个 TFM 的中性块存在且非空（TFM 由常量表钉——csproj 换 TFM 时本门禁先红，
   逼改动者确认这是有意的，而不是让锁悄悄错位）；
3. `<tfm>/win-x64` RID 块**存在**——缺块就是那次「只删不增」的 restore；
4. RID 块非空且 ⊇ `REQUIRED_IN_RID`（按 RID 解析的原生件必须留在钉定图上）；
5. 中性 ∪ RID ⊇ `REQUIRED_PINNED`（出货依赖整体得在锁里，否则「锁完整」是假话）。

第 5 条特意不校验**版本**：`SQLitePCLRaw.bundle_e_sqlite3` 目前解析为 2.1.11（NU1903/GHSA-2m69-gcr7-jv3q
只修了 3/4，R8-DEPS-3 已登记），版本下限要随 B7 的重锁**同批**加入才能既到货就常绿；
先钉一条必然红着的断言，只会被下一次「顺手放宽」吃掉。

退出码：0 通过 / 1 违规 / 2 环境错误（无锁文件）。
用法：`python scripts/verify_lock_rids.py`（仓库根运行）；`--print` 逐份报告。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# csproj 的 TargetFramework 单源（第 2 条判据用它定位块名）
TARGET_FRAMEWORKS = ("net10.0-windows7.0",)

# 发布制品的唯一 RID：Aegis Windows 正典栈只出 win-x64（ADR-009 单轨）
RUNTIME_ID = "win-x64"

# 有界登记：按 RID 解析、必须留在 RID 图里的原生件。
# 只写这两件是实测结果（`sqlite3` 原生二进制与 WebView2 loader），不是猜的。
REQUIRED_IN_RID = (
    "Microsoft.Web.WebView2",
    "SQLitePCLRaw.lib.e_sqlite3",
)

# 有界登记：出货依赖整体必须在锁里（中性块或 RID 块任一命中即算）。
# 这份集合是「制品运行期真的会加载的东西」，扩缩都必须是显式决定。
REQUIRED_PINNED = (
    "Microsoft.Data.Sqlite",
    "Microsoft.Web.WebView2",
    "SQLitePCLRaw.core",
    "SQLitePCLRaw.lib.e_sqlite3",
    "SQLitePCLRaw.provider.e_sqlite3",
    "SQLitePCLRaw.bundle_e_sqlite3",
)


def list_lock_files() -> list[Path]:
    """扫描面 = 工作树里实际存在的 `windows/**/packages.lock.json`。

    故意不走 `git ls-files`：本门禁要在「刚 restore 完、还没提交」的那一刻可用——
    那时改动尚未入索引，走索引检查等于放行最危险的那一次。
    """
    return sorted(
        path for path in ROOT.glob("windows/**/packages.lock.json")
        if "/obj/" not in path.as_posix() and "/bin/" not in path.as_posix()
    )


def display_rel(path: Path) -> str:
    """ROOT 之外的路径也要能报告（单测喂 tmp_path 时会走到这条）。
    早先这里直接 `relative_to(ROOT)`，一旦路径不在 ROOT 下就抛 ValueError——
    门禁把自己的判定路径当成崩溃理由，是「换个目录跑就红」的那类脆皮。"""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def package_names(block: object) -> set[str]:
    """锁 v1 的图值本身就是包映射；形态不对时返回空集（由调用方判违规）。"""
    return set(block) if isinstance(block, dict) else set()


def check_lock(path: Path) -> list[str]:
    rel = display_rel(path)
    try:
        # utf-8-sig：NuGet 可能写 BOM，带 BOM 时 json.loads 直接抛
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{rel}: 无法解析（{exc}）——判违规，不放行"]

    problems: list[str] = []
    if not isinstance(document, dict):
        return [f"{rel}: 顶层不是对象"]
    if document.get("version") != 1:
        problems.append(f"{rel}: version 不是 1（现值 {document.get('version')!r}）")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        problems.append(f"{rel}: dependencies 缺失或为空")
        return problems

    pinned: set[str] = set()
    for framework in TARGET_FRAMEWORKS:
        neutral = dependencies.get(framework)
        if neutral is None:
            problems.append(f"{rel}: 缺目标框架块 {framework!r}（csproj 换 TFM 了？）")
            continue
        neutral_names = package_names(neutral)
        if not neutral_names:
            problems.append(f"{rel}: {framework!r} 包映射为空")
            continue
        pinned |= neutral_names

        key = f"{framework}/{RUNTIME_ID}"
        rid_block = dependencies.get(key)
        if rid_block is None:
            # 这就是事故形态本身：restore 把整块删掉，diff 看着像「清理空白」
            problems.append(f"{rel}: 缺 RID 块 {key!r}（那次只删不增的 restore？）")
            continue
        rid_names = package_names(rid_block)
        if not rid_names:
            problems.append(f"{rel}: RID 块 {key!r} 包映射为空")
            continue
        missing = sorted(set(REQUIRED_IN_RID) - rid_names)
        if missing:
            problems.append(
                f"{rel}: RID 块 {key!r} 缺按 RID 解析的原生件 {missing}")

    unpinned = sorted(set(REQUIRED_PINNED) - pinned)
    if unpinned:
        problems.append(
            f"{rel}: 锁里没有这些出货依赖的钉定条目 {unpivot(unpinned)}"
            "——「锁很完整」在此处是假话")
    return problems


def unpivot(names: list[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def run(print_only: bool) -> int:
    locks = list_lock_files()
    if not locks:
        print("❌ 扫描面为空（0 份 packages.lock.json）——执行目录或 windows 布局异常，"
              "不作通过判定", file=sys.stderr)
        return 2
    problems: list[str] = []
    for path in locks:
        found = check_lock(path)
        if print_only:
            rel = display_rel(path)
            print(f"{'❌' if found else '✅'} {rel}")
            for line in found:
                print(f"   - {line}")
        problems.extend(found)
    if problems:
        for line in problems:
            print(f"❌ {line}", file=sys.stderr)
        return 1
    if not print_only:
        print(f"✅ RID 块门禁通过（{len(locks)} 份锁：RID 图与中性图都在，"
              f"原生件 {list(REQUIRED_IN_RID)} 已钉）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 .NET 锁文件的 RID 块与出货依赖钉定")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="逐份文件报告判定结果（退出码仍按违规计）")
    return run(parser.parse_args().print_only)


if __name__ == "__main__":
    sys.exit(main())

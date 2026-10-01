#!/usr/bin/env python3
"""跨平台同名发布资产去重。

三平台 dist 目录（windows/android/core）会产出同名文件
（build-metadata.json、SHA256SUMS.json、aegis_policy_core.dll 等）。
GitHub Release 不允许同名资产：softprops 上传第二个同名文件时
走 update-metadata 路径，在并发场景下触发 GitHub API 404，
导致 publish 步骤整体失败（v2.1.11 实测）。

处理方式：以第一个出现的目录为基准，其余目录中的同名文件
改名为 <平台名>-<原名>。目录顺序即调用参数顺序（先 windows）。

PY-211（2026-09-26 审计）——命名误导的取舍说明：
同平台内不同子目录的同名文件（如 android/arm64/x 与 android/win/x）也会
被加"平台前缀"改名——此时前缀是顶层目录名，并非"平台"语义，改出的
名字（android-foo.bin）会撒谎。两种修法中：
  ① 前缀改父目录链（android-arm64-foo.bin）——会改变资产命名契约，
     .github/workflows/release.yml 的重生成清单探测按
     "<platform>-SHA256SUMS.json" 前缀匹配，前缀位数变化会破坏该契约；
  ② 更新文档说明平台内去重行为（本注释）——零行为变更、不破坏
     release.yml 契约。
保守选择 ②：本脚本契约（首目录为基准 + 顶层目录名作前缀）保持不变，
明确记录"前缀 = 调用参数目录名（通常为平台），平台内子目录冲突亦复用
该前缀"的行为。若未来要改前缀逻辑，须同步 release.yml 探测命名。

用法：dedup_release_assets.py [--dry-run] <dist-windows> <dist-android> <dist-core>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    # PY-029：手工 argv 解析无 -h/--help——argparse 标准化（usage/自动报错）
    parser = argparse.ArgumentParser(
        description="跨平台同名发布资产去重（后出现的目录同名文件加平台前缀改名）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的改名，不落盘")
    parser.add_argument("dirs", nargs="+", metavar="DIR", help="各平台 dist 目录（顺序即优先级，先 windows）")
    args = parser.parse_args()
    dirs = [Path(d) for d in args.dirs]
    dry_run = args.dry_run
    for d in dirs:
        if not d.is_dir():
            print(f"ERROR: not a directory: {d}", file=sys.stderr)
            return 1

    seen: dict[str, Path] = {}
    renamed = 0
    for d in dirs:
        platform = d.name
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            base = f.name
            if base not in seen:
                seen[base] = f
                continue
            target = f.with_name(f"{platform}-{base}")
            # 极端情况：加前缀后仍撞名（前缀文件本身也在同目录）
            if target.exists():
                print(f"ERROR: rename target exists: {target}", file=sys.stderr)
                return 1
            if dry_run:
                print(f"[dry-run] renamed: {f.relative_to(d.parent)} -> {target.name}")
            else:
                f.rename(target)
                print(f"renamed: {f.relative_to(d.parent)} -> {target.name}")
            # PY-219（2026-10-01 审计）：改名产物此前不写 seen——后续目录中
            # 原生同名资产（如第三方目录本就有 <platform>-x）再冲突时不再
            # 改名，最终上传仍撞名 404（防的正是该场景）。改名即入账。
            seen[target.name] = target
            renamed += 1

    print(f"OK: {renamed} duplicate(s) renamed{' (dry-run, no changes)' if dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

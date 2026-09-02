#!/usr/bin/env python3
"""跨平台同名发布资产去重。

三平台 dist 目录（windows/android/core）会产出同名文件
（build-metadata.json、SHA256SUMS.json、aegis_policy_core.dll 等）。
GitHub Release 不允许同名资产：softprops 上传第二个同名文件时
走 update-metadata 路径，在并发场景下触发 GitHub API 404，
导致 publish 步骤整体失败（v2.1.11 实测）。

处理方式：以第一个出现的目录为基准，其余目录中的同名文件
改名为 <平台名>-<原名>。目录顺序即调用参数顺序（先 windows）。

用法：dedup_release_assets.py [--dry-run] <dist-windows> <dist-android> <dist-core>
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    dirs = [Path(arg) for arg in args if arg != "--dry-run"]
    if not dirs:
        print("usage: dedup_release_assets.py [--dry-run] <dir1> <dir2> ...", file=sys.stderr)
        return 2
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
            renamed += 1

    print(f"OK: {renamed} duplicate(s) renamed{' (dry-run, no changes)' if dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

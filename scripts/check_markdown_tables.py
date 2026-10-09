#!/usr/bin/env python3
"""check_markdown_tables.py —— R8-DOC-19（第八轮 2026-10-10）：GFM 表格形状门禁。

判据：一张表里**每一行的列数必须等于表头的列数**。列按未转义的 `|` 切分——
GFM 的表格解析器不认代码段里的裸竖线：`` `… || true` `` 出现在表格单元里就是
两个额外分隔符，整行向右错位、超出表头的那几列被丢弃，**内容静默消失**（渲染后
读不出来，源码里却在）。本仓台账正是「机器可解析的事实源」，行错位等于记账漏项。

扫描面：git ls-files 收口的受管 *.md（可用 --paths 指定子集，与单测同口径）。

跳过：
- 围栏代码块（``` / ~~~ 之间）——文档里的 ASCII 框图不是表；
- 没有分隔行（`| --- | --- |`）的管道对齐块——同样不是表（GFM 要求分隔行）；
- 反斜杠转义的 `\\|`——按内容计，不按分隔计。

逐条判据都有反向证（tests/python/markdown_table_gate_test.py）：植入一列之差不被
判出，这条门禁就只是装饰。

用法：
    python scripts/check_markdown_tables.py             # CI（contracts.yml）与本地同口径
    python scripts/check_markdown_tables.py --paths a.md b.md

退出码：0=全部表形一致 / 1=存在错位行（逐条列出 文件:行号 与列数）/
2=环境错误（git 不可用、指定文件缺失、扫描面为空、扫到了表却一张都没有）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 围栏代码块开闭行（``` 或 ~~~，允许至多 3 空格缩进）——与 check_markdown_links 同口径
FENCE_LINE = re.compile(r"^\s{0,3}(```|~~~)")
# 表格分隔单元格：`---` / `:---` / `---:` / `:---:`
DELIMITER_CELL = re.compile(r"^:?-+:?$")
# 转义竖线的占位符（不会出现在正文里）
ESCAPED_PIPE = "\x00"


def list_markdown_files(explicit: list[str] | None) -> list[Path]:
    """--paths 给定则用给定面（单测注入），否则 git ls-files 收口受管 *.md。"""
    if explicit:
        missing = [p for p in explicit if not (ROOT / p).is_file()]
        if missing:
            print(f"❌ 指定文件缺失：{', '.join(missing)}", file=sys.stderr)
            raise SystemExit(2)
        return [ROOT / p for p in explicit]
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=str(ROOT), check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"❌ git ls-files 失败：{result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [ROOT / p for p in paths]


def split_cells(line: str) -> list[str] | None:
    """表格行 → 单元格列表；非表格行返回 None。转义竖线按内容计。"""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    body = stripped[1:]
    if body.endswith("|"):
        body = body[:-1]
    body = body.replace("\\|", ESCAPED_PIPE)
    return [cell.strip() for cell in body.split("|")]


def is_delimiter_row(cells: list[str]) -> bool:
    return bool(cells) and all(DELIMITER_CELL.match(cell) for cell in cells)


def check_file(path: Path, violations: list[str]) -> int:
    """校验一个 .md 里的所有表；返回该文件的表数。"""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        violations.append(f"{path.relative_to(ROOT)}: <读取失败> —— {exc}")
        return 0
    tables = 0
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if FENCE_LINE.match(line):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        cells = split_cells(line)
        following = split_cells(lines[index + 1]) if index + 1 < len(lines) else None
        if not (cells and following and is_delimiter_row(following)):
            index += 1
            continue
        tables += 1
        expected = len(cells)
        if len(following) != expected:
            violations.append(
                f"{path.relative_to(ROOT)}:{index + 2}: 分隔行 {len(following)} 列 ≠ 表头 {expected} 列")
        cursor = index + 2
        while cursor < len(lines):
            row = split_cells(lines[cursor])
            if row is None:
                break
            if len(row) != expected:
                violations.append(
                    f"{path.relative_to(ROOT)}:{cursor + 1}: 该行 {len(row)} 列 ≠ 表头 {expected} 列"
                    f"（代码段里的裸竖线？改用 \\| 转义）")
            cursor += 1
        index = cursor
    return tables


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GFM 表格列数一致性门禁（R8-DOC-19）")
    parser.add_argument("--paths", nargs="*", help="仅校验给定相对路径（单测与局部复查用）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    files = list_markdown_files(args.paths)
    if not files:
        # 空面 = 没有任何表被判定：git 索引异常 / 在错误目录执行 / 受管面被整体移出
        print("❌ 扫描面为空（0 个 .md）——不作通过判定", file=sys.stderr)
        return 2
    violations: list[str] = []
    tables = sum(check_file(path, violations) for path in files)
    if violations:
        print(f"❌ 表格形状门禁失败（{len(violations)} 处，共扫描 {tables} 张表）：")
        for item in sorted(violations):
            print(f"  - {item}")
        return 1
    if tables == 0:
        print(f"❌ 扫了 {len(files)} 个 .md 却没识别出任何表格——表形判定形同未运行", file=sys.stderr)
        return 2
    print(f"✅ 表格形状门禁通过（{len(files)} 个 .md、{tables} 张表，逐行列数与表头一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

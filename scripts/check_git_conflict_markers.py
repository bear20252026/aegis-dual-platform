#!/usr/bin/env python3
"""check_git_conflict_markers.py —— Q74 R9-DOC-27：git 冲突标记门禁。

全仓受管文本的 git 冲突标记存在性校验（结构污染 fail-closed）：

- 校验行首 `<<<<<<< ` 与 `>>>>>>> ` 零命中（`=======` 单独存在是合法的
  setext 标题下划线，不能一并算——判据必须写窄）；
- 扫描面：git ls-files 收口的受管文本文件（.md / .py / .rs / .kt / .cs /
  .js / .ts / .json / .yaml / .yml / .toml / .xml / .gradle / .kts / .sh）；
- 跳过：.git 目录、二进制文件、无扩展名文件。

背景：
    R9-B98 rebase 时发现 master 的台账里躺着一处 git 冲突标记
    （`docs/audit/full-audit-2026-10-10-round9.md` 第 1809 行是
    `>>>>>>> origin/master`）——某次合并手工解冲突时漏删，之后一路随
    squash 进主干。读者看到它只会以为是台账自己的分隔线，实际它的意思是
    「这里曾经有人没解完冲突，而且没人核对过」。

    同一形状的失账本仓已经记过三次：
    - §3.50 的「引用一个不存在的小节」
    - R9-B62 的「判据写好了执行面没人核」
    - Q69 的「纪律写在标题里没人判」
    这是第四条：**结构污染没人判**。

用法：
    python scripts/check_git_conflict_markers.py    # CI（contracts.yml）与本地同口径

退出码：0=全部文件无冲突标记 / 1=存在冲突标记（逐条列出 文件:行号）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# git 冲突标记（行首）
CONFLICT_START = re.compile(r"^<<<<<<< ")
CONFLICT_END = re.compile(r"^>>>>>>> ")
# 注意：`=======` 单独存在是合法的 setext 标题下划线，不能一并算

# 受管文本文件扩展名（与 contracts.yml 的扫描面一致）
TEXT_EXTENSIONS = {
    ".md", ".py", ".rs", ".kt", ".cs", ".js", ".ts",
    ".json", ".yaml", ".yml", ".toml", ".xml",
    ".gradle", ".kts", ".sh",
}


def list_managed_text_files() -> list[Path]:
    """git ls-files 收口扫描面——返回绝对路径。"""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT), check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"error: git ls-files failed: {result.stderr}", file=sys.stderr)
        return []
    
    files = []
    for line in result.stdout.splitlines():
        path = Path(line)
        if path.suffix in TEXT_EXTENSIONS:
            files.append(ROOT / path)
    return files


def check_file_for_conflict_markers(path: Path) -> list[tuple[int, str]]:
    """检查单个文件的冲突标记——返回 (行号, 行内容) 列表。"""
    hits = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.splitlines(), start=1):
            if CONFLICT_START.match(line) or CONFLICT_END.match(line):
                hits.append((i, line))
    except (OSError, UnicodeDecodeError):
        # 读取失败跳过（可能是二进制文件或权限问题）
        pass
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 git 冲突标记（Q74 R9-DOC-27）")
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="输出所有扫描的文件数",
    )
    args = parser.parse_args()

    files = list_managed_text_files()
    
    if args.verbose:
        print(f"扫描 {len(files)} 个受管文本文件...")

    violations = []
    for path in files:
        hits = check_file_for_conflict_markers(path)
        if hits:
            rel_path = path.relative_to(ROOT)
            for line_no, line_content in hits:
                violations.append(f"{rel_path}:{line_no}: {line_content}")

    if violations:
        print(f"error: 发现 {len(violations)} 处 git 冲突标记（应为 0）：", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\n冲突标记通常出现在合并/变基冲突后未完全解决时。",
            "请解决冲突后重新提交。",
            file=sys.stderr,
        )
        return 1

    if args.verbose:
        print("✓ 未发现 git 冲突标记")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""check_doc_claims.py —— 第八轮 B8（R8-DOC 家族）：文档「计数类声明」与实树对账。

失效模式：README/docs 里写死的 workflow 数量是**陈述**，实树变化后没人回头改——
同一件事连续三轮复发（WB-214 把 README 对齐为 13 → 第六轮 R6 记为「闭环即回归」
（其后新增两个 workflow 而计数静默漂移）→ 第八轮实测仍有 8 处与实树不符（7 处写 13、
1 处写 6），实树 15）。
本门禁判的是「文档说的数 = 实树的数」，让这类陈述不再靠人记得回头改。

口径：
- 扫描面 = `git ls-files` 收口的全部受管 `.md`（README/CHANGELOG/docs/** 全量）；
  `legacy/` 整树排除——只读冻结归档，不与正典实树对账；
- 「N 个 workflow」形态的声明逐条与 `.github/workflows/*.{yml,yaml}` 实际文件数比对；
- **带日期的标题语境不比对**：审计台账（`docs/audit/**`）与 CHANGELOG 的日期条目是
  「扫描/发布当日实树」的快照，回改等于篡改历史。判据只有一条——**声明的标题链上
  任一级标题含 `YYYY-MM-DD`**。不设「本行含日期即豁免」：实测那样会放过
  `architecture-overview.md:85`（「**13 workflow 分层**（WB-160，2026-10-01 审计对齐实树）」）
  与 `b4-enable-notes.md:2`（日期是文档生日、句子却用「现发布链已演进为…」）
  两条现行陈述，行内日期不该成为豁免理由；
- 实树 workflow 数为 0 / 扫描面为空 / **非历史性声明数为 0** ⇒ exit 2。
  第三条是关键：正则被改坏、或全部声明都被判成历史性时，「什么都没判」曾被当
  「全通过」（R7-TOOL-04 / R8-PY-08 同族掏空面）。

退出码：0=全部一致 / 1=存在失实计数（逐条列出 文件:行号）/ 2=环境错误（含空面）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

# 归档栈不与正典实树对账（只读冻结——CLAUDE.md「legacy 冻结」口径）
EXCLUDED_PREFIXES = ("legacy/",)

# 「N 个/条 workflow」「N workflow」——数字前不许有 - 或单词字符，
# 否则 "WB-214 workflow 计数回归" 这类条目 ID 会被误读成计数声明
COUNT_CLAIM = re.compile(r"(?<![-\w/])(\d{1,3})\s*(?:个|条)?\s*[Ww]orkflows?\b")
# 日期判据：ISO 形态 YYYY-MM-DD（台账文件名、标题里的发布日期、条目日期都用它）
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FENCE_LINE = re.compile(r"^\s{0,3}(```|~~~)")
HEADING_LINE = re.compile(r"^#{1,6}\s")


def workflow_count() -> int:
    """实树 workflow 文件数（yml/yaml 双扩展名都算）。"""
    return len([p for p in WORKFLOWS_DIR.glob("*")
                if p.is_file() and p.suffix in (".yml", ".yaml")])


def list_markdown_files() -> list[Path]:
    """git ls-files 收口扫描面——返回仓库根相对路径字符串（便于报告与排除）。"""
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=str(ROOT), check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"❌ git ls-files 失败：{result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines()
            if line.strip() and not line.strip().startswith(EXCLUDED_PREFIXES)]


def extract_claims(text: str) -> list[tuple[int, int, bool]]:
    """单文件的计数声明提取：返回 (行号, 数字, 是否属带日期记录) 列表。

    围栏代码块内的行不解析（示例/图示不是陈述）；历史性判据取「声明的标题链上任一级
    含 YYYY-MM-DD」——CHANGELOG 的版本标题自带日期，其下的 `### 工程` 等无日期子节
    仍属该版本条目，只认「最近一级标题」会把它们错判成现行陈述。
    """
    claims: list[tuple[int, int, bool]] = []
    in_fence = False
    heading_stack: list[tuple[int, bool]] = []   # (标题级数, 该级标题是否带日期)
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_LINE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if HEADING_LINE.match(line):
            level = len(line) - len(line.lstrip("#"))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, bool(ISO_DATE.search(line))))
        if not line.strip():
            continue
        chain_dated = any(dated for _level, dated in heading_stack)
        for match in COUNT_CLAIM.finditer(line):
            claims.append((lineno, int(match.group(1)), chain_dated))
    return claims


def violations_for(rel: str, claims: list[tuple[int, int, bool]], actual: int) -> list[str]:
    """判定：非历史性（标题链无日期）的计数声明必须与实树一致；历史性声明跳过。"""
    out: list[str] = []
    for lineno, stated, dated in claims:
        if dated:
            continue
        if stated != actual:
            out.append(f"{rel}:{lineno} 声明 {stated} 个 workflow，实树为 {actual}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="文档计数声明与实树对账门禁（第八轮 B8）")
    parser.parse_args(sys.argv[1:] if argv is None else argv)

    actual = workflow_count()
    if actual == 0:
        print(f"❌ 实树 workflow 数为 0（{WORKFLOWS_DIR}）——不作通过判定", file=sys.stderr)
        return 2

    files = list_markdown_files()
    if not files:
        print("❌ 文档门禁扫描面为空（0 个 .md）——不作通过判定", file=sys.stderr)
        return 2

    problems: list[str] = []
    judged = 0
    historical = 0
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        claims = extract_claims(text)
        judged += len([c for c in claims if not c[2]])
        historical += len([c for c in claims if c[2]])
        problems.extend(violations_for(rel, claims, actual))

    if judged == 0:
        # 掏空面：正则失配、或声明全部被判历史性 ⇒ 本门禁零判定，不得报绿
        print("❌ 未提取到任何「非带日期记录」的 workflow 计数声明——"
              "扫描面/正则发生变化即门禁失效，不作通过判定（exit 2）", file=sys.stderr)
        return 2

    if problems:
        print(f"❌ 文档计数声明与实树不符（{len(problems)} 处，实树 {actual} 个 workflow）：")
        for item in sorted(problems):
            print(f"  - {item}")
        return 1
    print(f"✅ 文档计数声明与实树一致（实树 {actual} 个 workflow；"
          f"判定 {judged} 处，另有 {historical} 处带日期记录按当日快照豁免）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

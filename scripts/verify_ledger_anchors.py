#!/usr/bin/env python3
"""verify_ledger_anchors.py —— §五 **未划线**队列行的 `file:line` 锚必须存在且解析得到（R9-B81 / Q69 第一半）。

要防的不是「某条没修」，而是**队列行引用了一个实树里不存在的位置**。§五 的标题从第八轮起就
写着「必须带 file:line」，但那条纪律此前没有任何门禁判它——三件事都没人核：这行到底带没带锚、
锚指的文件还在不在、那一行现在是不是写着被引用的东西。实测规模（R9-B80 现读）：62 条队列行里
49 条带锚、共 328 处引用，另有 13 条一个行号锚都没有；而 #218 那一批往被引用的 Kotlin 文件里
插了 7 行注释，同一提交写的 `:76-77`／`:120-126` 当场漂成 `:83-84`／`:127-133`，两道既有门禁
（本文件同族的 `verify_ledger_queue_status.py` 与 `check_doc_claims.py`）都放行。

判据四条，每条都在 `tests/python/ledger_anchors_test.py` 里以内存注入证伪：
1. 活行（未划线的队列行）至少有一处 `` `path.ext:NN[-MM]` `` 锚；
2. 锚能取到文件：整条相对路径逐字命中，或裸文件名在实树**唯一**命中——同名多处判红，因为
   `broker.rs:120` 这种写法要下一个读者自己去猜是哪一个 `broker.rs`；
3. 行号落在文件行数内，且 `NN ≤ MM`；
4. 引用的区间里至少有一行非空——指到五个空行等于没指。

**范围只判活行是有意的**，不是偷懒：已划线的行引的是**当时**的行号，代码一改必然悬空，
要么全量改写历史（违反「翻转不静默删行」），要么给旧批次开一张豁免表（豁免面就是下一个假绿源）。
所以历史条目仍由 §三 的批次记录自证，本门禁只管「下一轮还要动手的活行」。接入时实测现树
8 条活行共 20 处锚，全部可解析 ⇒ 本门禁**接入即绿**，红只会在下一批台账写下错锚时出现。

退出码：0=通过 / 1=违规（零锚、悬空、越界、多义、空区间）/ 2=环境或判定面塌缩
（台账缺失、§五 缺失、活行数或锚数为 0——「什么都没判到」不等于「判过了且没问题」）。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import verify_ledger_queue_status as queue

ROOT = Path(__file__).resolve().parents[1]
LEDGER_GLOB = "docs/audit/full-audit-*.md"
PRUNED = {".git", ".gradle", ".venv", "__pycache__", "bin", "build", "dist", "node_modules", "target"}
EXTENSIONS = (
    "kt", "kts", "cs", "py", "rs", "js", "mjs", "html", "json",
    "md", "yml", "yaml", "xml", "toml", "csv",
)
ANCHOR = re.compile(
    r"([A-Za-z0-9_./\-]+\.(?:" + "|".join(EXTENSIONS) + r")):(\d+)(?:-(\d+))?",
)


def name_index() -> dict[str, list[Path]]:
    """裸文件名 → 实树路径（剪掉构建面与构建产物）。多义的裸名由判据 ② 处理，不在这里猜。"""
    out: dict[str, list[Path]] = {}
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in PRUNED]
        for name in files:
            out.setdefault(name, []).append(Path(base) / name)
    return out


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return -1


def non_blank_in_range(path: Path, start: int, end: int) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False
    return any(line.strip() for line in lines[start - 1:end])


def resolve(raw: str, index: dict[str, list[Path]]) -> list[Path]:
    exact = ROOT / raw
    if exact.is_file():
        return [exact]
    return index.get(Path(raw).name, [])


def check_row(head: str, block: str, index: dict[str, list[Path]]) -> tuple[list[str], int]:
    """一条活行 → (违规, 锚数)。"""
    problems: list[str] = []
    anchors = list(ANCHOR.finditer(block))
    if not anchors:
        problems.append(f"活行没有任何 file:line 锚（§五 标题要求「必须带 file:line」）：{head[:70]}")
        return problems, 0
    for match in anchors:
        raw, nn, mm = match.group(1), int(match.group(2)), int(match.group(3) or match.group(2))
        hits = resolve(raw, index)
        label = f"{raw}:{match.group(2)}"
        if not hits:
            problems.append(f"锚指向实树里没有的文件（改名/删除后没回读）：{label} ← {head[:44]}")
            continue
        if len(hits) > 1:
            problems.append(
                f"裸文件名在实树有 {len(hits)} 处同名，锚无法唯一解析（请写整条相对路径）："
                f"{label} ← {head[:44]}")
            continue
        path = hits[0]
        total = line_count(path)
        if nn < 1 or mm < nn or mm > total:
            problems.append(
                f"行号越界（该文件现 {total} 行）：{label} ← {head[:44]}"
                "——代码增删后没回读的锚就是这种形态")
            continue
        if not non_blank_in_range(path, nn, mm):
            problems.append(f"引用的区间全是空行，等于没指：{label} ← {head[:44]}")
    return problems, len(anchors)


def violations(text: str, index: dict[str, list[Path]] | None = None) -> tuple[list[str], int, int]:
    """整份台账 → (违规, 活行数, 锚总数)。"""
    index = index if index is not None else name_index()
    problems: list[str] = []
    rows = 0
    anchors = 0
    for head, block in queue.queue_blocks(text):
        if head.startswith("- ~~"):
            continue  # 划线行不参与（范围口径见模块 docstring）
        rows += 1
        found, count = check_row(head, block, index)
        problems += found
        anchors += count
    return problems, rows, anchors


def run() -> int:
    ledgers = sorted(ROOT.glob(LEDGER_GLOB))
    if not ledgers:
        print(f"[环境错误] 找不到任何台账：{LEDGER_GLOB}", file=sys.stderr)
        return 2
    judged = 0
    problems: list[str] = []
    index = name_index()
    for ledger in ledgers:
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        if not queue.QUEUE_HEAD.search(text):
            continue
        found, rows, anchors = violations(text, index)
        if rows == 0 or anchors == 0:
            print(
                f"[环境错误] {ledger.name} 的 §五 数出活行 {rows} 条、锚 {anchors} 处——"
                "判定面塌了，不作通过判定", file=sys.stderr)
            return 2
        judged += 1
        problems += [f"{ledger.name}: {line}" for line in found]
    if judged == 0:
        print("[环境错误] 没有任何台账带 §五 队列段——本判据无事可做就等于没接上", file=sys.stderr)
        return 2
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    print("[ok] 活行 file:line 锚可解析性对账通过"
          f"（{judged} 份台账；实树索引 {len(index)} 个文件名；违规 0 条）")
    return 0


if __name__ == "__main__":
    sys.exit(run())

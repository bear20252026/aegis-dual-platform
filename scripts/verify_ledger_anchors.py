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

退出码：0=通过 / 1=违规（零锚、悬空、越界、多义、空区间、符号不在代码里、棘轮对不上）
/ 2=环境或判定面塌缩（台账缺失、§五 缺失、活行数或锚数为 0——「什么都没判到」不等于「判过了且没问题」）。

R9-B83 加的两条（Q69 第③条候选判据落地，第②条正式判成**不做**）：
5. `` `path.ext::symbolName` `` 形式的**符号锚**，其符号必须在 `strip_comments` 之后的代码里真出现
   （口径单源 `scripts/text_anchors.py`，R9-B45）——只在注记里提到不算证据（R9-B39 那个病）。
6. 带可解析符号锚的**活行行数**必须恰好等于 `MIN_SYMBOL_ROWS`。用等号而不是下界是有意的：下界只拦
   「退回去」，等号还拦「顺手多锚了几行却没登记」——这张表是「还剩多少事」的唯一依据，脱钩一次就得
   靠人现读才发现（§3.82 第 7 点刚演示过一次）。
7. 为什么**不做**②「引用区间内至少要出现条目正文里的一个标识符 token」：本仓有把被禁形态逐字抄进
   注释的传统（R9-B45、§3.22 的 frame-ancestors 注记、`InstalledBuildMarkerTests`），那条判据会把
   解释历史写的条目打红，而为变绿最容易被做的是**删注记**——丢掉的正是不想让人重犯的那段上下文。
   符号锚在不依赖行号的方向上判掉了同一件事：符号改名或删除会红，注记怎么写都不会红。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import verify_ledger_queue_status as queue
from text_anchors import strip_comments

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
# R9-B83：符号锚 `path.ext::symbolName`——行号会随增删漂移，符号名不会（Q69 第③条候选判据）。
SYMBOL_ANCHOR = re.compile(
    r"([A-Za-z0-9_./\-]+\.(?:" + "|".join(EXTENSIONS) + r"))::([A-Za-z_][A-Za-z0-9_]*)",
)
# 带可解析符号锚的活行**行数**必须恰好等于这个登记值（棘轮，两个方向都判红）。
# 等号而不是下界是有意的：下界只拦「退回去」，等号还拦「多锚了几行却没登记」。
# 结一条活案会把这个数**调小**（R9-B83 就是 8 → 7，Q69 划线后自动退出判定面）——这不是负担，
# 而是这张表与 §五 真实规模唯一会被机器核对的耦合点：脱钩一次就要靠人现读才发现（§3.82 第 7 点）。
MIN_SYMBOL_ROWS = 3


def name_index() -> dict[str, list[Path]]:
    """裸文件名 → 实树路径（剪掉构建面与构建产物）。多义的裸名由判据 ② 处理，不在这里猜。"""
    out: dict[str, list[Path]] = {}
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in PRUNED]
        for name in files:
            out.setdefault(name, []).append(Path(base) / name)
    return out


def _rel(path: Path) -> str:
    """给 `strip_comments` 一个能判语言的路径；索引给到 ROOT 外面时退回裸名
    （只影响「`#` 算不算注释」这一条按扩展名启用的口径，不影响命中与否）。"""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def code_of(rel_path: str) -> str:
    """剔注释后的代码文本——口径单源在 `text_anchors.strip_comments`（R9-B45）。
    符号只在注记里出现**不算**：注记会解释历史写法，把解释当证据就是 R9-B39 那个病。
    不加缓存：判据读的是文件当下内容，缓存会让「同一进程里换 ROOT 的注入用例」读到上一条的字节。"""
    try:
        raw = (ROOT / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return strip_comments(raw, rel_path)


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


def check_row(
    head: str, block: str, index: dict[str, list[Path]],
) -> tuple[list[str], int, bool]:
    """一条活行 → (违规, 锚数, 是否带可解析的符号锚)。"""
    problems: list[str] = []
    anchors = list(ANCHOR.finditer(block))
    symbols = list(SYMBOL_ANCHOR.finditer(block))
    if not anchors and not symbols:
        problems.append(f"活行没有任何 file:line 锚（§五 标题要求「必须带 file:line」）：{head[:70]}")
        return problems, 0, False
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
    symbol_ok = False
    for match in symbols:
        raw, symbol = match.group(1), match.group(2)
        hits = resolve(raw, index)
        label = f"{raw}::{symbol}"
        if not hits:
            problems.append(f"符号锚的文件在实树里不存在：{label} ← {head[:44]}")
            continue
        if len(hits) > 1:
            problems.append(f"符号锚用了多义裸名（{len(hits)} 处同名）：{label} ← {head[:44]}")
            continue
        code = code_of(_rel(hits[0]))
        if not re.search(rf"\b{re.escape(symbol)}\b", code):
            problems.append(
                f"符号锚在**剔注释后的代码**里找不到「{symbol}」：{label} ← {head[:44]}"
                "——注记里提到它不算证据（R9-B39），符号改名/删除必须同批改锚")
            continue
        symbol_ok = True
    return problems, len(anchors) + len(symbols), symbol_ok


def violations(
    text: str, index: dict[str, list[Path]] | None = None,
) -> tuple[list[str], int, int, int]:
    """整份台账 → (违规, 活行数, 锚总数, 带可解析符号锚的活行数)。"""
    index = index if index is not None else name_index()
    problems: list[str] = []
    rows = 0
    anchors = 0
    symbol_rows = 0
    for head, block in queue.queue_blocks(text):
        if head.startswith("- ~~"):
            continue  # 划线行不参与（范围口径见模块 docstring）
        rows += 1
        found, count, has_symbol = check_row(head, block, index)
        problems += found
        anchors += count
        symbol_rows += 1 if has_symbol else 0
    return problems, rows, anchors, symbol_rows


def ratchet_message(symbol_rows: int) -> str:
    """棘轮的成句——`run()` 与用例共用同一条措辞，免得两处各写一份判据解释。

    计数**只在 `run()` 里判**：`violations()` 被内存注入用例逐条调用，那些 fixture 只有一两行
    活行，把全局计数放进去会让每一条注入都被牵连成「还差 6 条」——那既不是那条用例要判的东西，
    也会把真正的那一条违规埋掉。
    """
    return (f"带可解析符号锚的活行数是 {symbol_rows}，登记值是 {MIN_SYMBOL_ROWS}——"
            "两个方向都要同批改：退回去要红，多锚了不登记也要红")


def run() -> int:
    ledgers = sorted(ROOT.glob(LEDGER_GLOB))
    if not ledgers:
        print(f"[环境错误] 找不到任何台账：{LEDGER_GLOB}", file=sys.stderr)
        return 2
    judged = 0
    problems: list[str] = []
    index = name_index()
    symbol_rows_total = 0
    for ledger in ledgers:
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        if not queue.QUEUE_HEAD.search(text):
            continue
        found, rows, anchors, symbol_rows = violations(text, index)
        if rows == 0 or anchors == 0:
            print(
                f"[环境错误] {ledger.name} 的 §五 数出活行 {rows} 条、锚 {anchors} 处——"
                "判定面塌了，不作通过判定", file=sys.stderr)
            return 2
        judged += 1
        symbol_rows_total += symbol_rows
        problems += [f"{ledger.name}: {line}" for line in found]
    if judged == 0:
        print("[环境错误] 没有任何台账带 §五 队列段——本判据无事可做就等于没接上", file=sys.stderr)
        return 2
    if symbol_rows_total != MIN_SYMBOL_ROWS:
        problems.append(ratchet_message(symbol_rows_total))
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    print("[ok] 活行 file:line 锚可解析性对账通过"
          f"（{judged} 份台账；实树索引 {len(index)} 个文件名；"
          f"符号锚行 {MIN_SYMBOL_ROWS} 条与登记值一致；违规 0 条）")
    return 0


if __name__ == "__main__":
    sys.exit(run())

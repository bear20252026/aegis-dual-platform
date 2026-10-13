#!/usr/bin/env python3
"""verify_ledger_queue_status.py —— 台账 §五 队列的**状态可读性**门禁（R9-B52 / 第九轮自查）。

要防的不是「某条没修」，而是**队列自己报错了规模**：第九轮 §三 的每条落地都会在 §五 把行划掉
（`- ~~Qn …~~`）并留一个 `§3.nn` 指针。这件事此前全靠人记得做，于是出现两种漂移：

1. **声称落地却没有划线**（本轮现读到 6 行：Q12 / Q13 / Q14 / Q22 / Q47 / Q39-Q46 都写着
   「本批已落地」，行头却还是开放形态）⇒ 下一轮按 §五 数「还剩多少事」会**虚高**，
   还会把已经做完的项目再派一次子代理——第八轮的规模虚高正是这么来的。
2. **划了线但指针不成立**（引用一个文件里不存在的 `### 3.nn`）⇒ 闭环声明变成不可回读的假账。
   这不是假想：本批写 §3.50 时发现 §3.48 **整节缺失**，而 §二、§四 有三处文字在引用它——
   引用一个不存在的小节，比不写指针更坏，因为它读起来像已经交代过。

判据（每条都在 tests/python/ledger_queue_status_test.py 里以内存注入证伪）：
- 队列行 = 顶层 `- Qn` / `- ~~Qn` 形态；一条行的「块」= 从该行到下一条队列行或下一个 `### ` 标题。
- 未划线的行必须含一个**开放状态词**（词汇表见 `OPEN_STATE_WORDS`）：待裁决 / 待定稿 / 待设备 /
  部分闭环 / 需给话 …。没有状态词的开放行＝下一个读者无法判断它到底要不要动手。
- 划线的行必须含至少一个能在同一文件里解析到的 `§3.nn` 指针。
- 判定面塌缩（一份带 `## 五、` 标题的台账里一条队列行都数不出来）⇒ 退出 2，不判「通过」。

退出码：0=通过 / 1=状态词缺失或指针悬空 / 2=环境或判定面异常。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_GLOB = "docs/audit/full-audit-*.md"
# 只认「待回读队列」这一节的队列行：轮 6/7/8 的 `## 五、` 是别的主题（被推翻结论、P3 抽样、
# 既往声明核验），把它们算进判定面就是拿判据去判不存在的形状（实测：轮 6 会当场触发塌缩分支）。
QUEUE_HEAD = re.compile(r"^## 五、待回读队列", re.M)
ROW_HEAD = re.compile(r"^- (?:~~)?Q\d+", re.M)
STRUCK = re.compile(r"^- ~~Q\d+", re.M)
POINTER = re.compile(r"§(3\.\d+)")
HEADING = re.compile(r"^### (3\.\d+)", re.M)
# 开放状态词：一行「没划线」的队列项必须从中挑一个写明它为什么还开着。
OPEN_STATE_WORDS = (
    "待裁决",
    "待定稿",
    "待回读",
    "待实测",
    "待设备",
    "需设备",
    "需硬件",
    "需给话",
    "需用户裁决",
    "需产品决策",
    "需另行",
    "需定稿",
    "部分闭环",
    "登记不顺手",
    "不顺手做",
    "仍开着",
    "未排期",
    "不在本批",
)


def queue_blocks(text: str) -> list[tuple[str, str]]:
    """§五 队列段内的队列行 → (行首文本, 整块文本)。

    块的两端都有边界：行到行，段到**下一个 `## ` 标题**。少了后者，§五 最后一条行会把
    §六/§七 的正文当成自己的状态说明（那些段落里出现「待裁决」是常态），
    判据就在最该生效的那一行上失效。
    """
    start = QUEUE_HEAD.search(text)
    if not start:
        return []
    after = text[start.end():]
    stop = re.search(r"^## ", after, re.M)
    body = text[start.start(): start.end() + stop.start()] if stop else text[start.start():]
    rows = list(ROW_HEAD.finditer(body))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(rows):
        end = rows[index + 1].start() if index + 1 < len(rows) else len(body)
        block = body[match.start():end]
        blocks.append((block.splitlines()[0], block))
    return blocks


def violations(text: str) -> list[str]:
    heads = set(HEADING.findall(text))
    problems: list[str] = []
    for header, block in queue_blocks(text):
        pointers = set(POINTER.findall(block))
        if STRUCK.match(header):
            if not (pointers & heads):
                problems.append(
                    f"已划线的队列项没有能解析到的 §3.nn 指针（写到的指针：{sorted(pointers) or '无'}）"
                    f"——闭环声明必须可回读：{header[:70]}")
            continue
        if not any(word in block for word in OPEN_STATE_WORDS):
            problems.append(
                f"未划线的队列项没有开放状态词（{header[:70]}）——"
                "要么它已落地该划线并留 §3.nn 指针，要么它得写明为什么还开着（待裁决 / 待设备 / 部分闭环 …）")
    return problems


def run() -> int:
    ledgers = sorted(ROOT.glob(LEDGER_GLOB))
    if not ledgers:
        print(f"[环境错误] 找不到任何台账：{LEDGER_GLOB}", file=sys.stderr)
        return 2
    scanned = 0
    problems: list[str] = []
    for ledger in ledgers:
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        if not QUEUE_HEAD.search(text):
            continue  # 早期轮次没有 §五 队列段（§三 直列批次），不参与本判据
        scanned += 1
        rows = queue_blocks(text)
        if not rows:
            print(f"[环境错误] {ledger.name} 有 `## 五、` 却数不出一条 `- Qn` 队列行——判定面塌了", file=sys.stderr)
            return 2
        found = violations(text)
        for line in found:
            problems.append(f"{ledger.name}: {line}")
    if scanned == 0:
        print("[环境错误] 没有任何台账带 §五 队列段——本判据无事可做就等于没接上", file=sys.stderr)
        return 2
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    print(f"[ok] 队列状态可读性对账通过（{scanned} 份带 §五 的台账；划线的都有 §3.nn 指针，未划线的都写明了为什么开着）")
    return 0


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
"""verify_ledger_decision_status.py —— 台账 §四「待用户定稿」的可判红对账（R9-B92 / R9-DOC-25）。

要防的不是「某件事还没定」，而是**「哪些事要人给话」这张清单自己报错**。§五 从 R9-B52 起有状态判据、
§五 活行从 R9-B81 起有锚可解析性，§四 一直没有：`check_doc_claims.py` 只认「N 个 workflow」形态，
两条台账门禁都只扫 §五。§3.85 第 6 点因此留了一条残余缺口（「待用户定稿」这一节里的状态词没有任何
东西判它）。本批现读 §四，四条过期当场现形，判据就是照这四种形状写的：
① 已被书面结论收走的处方仍列在「真未决」里；② 同一节里一处写「已定稿并落地」、另一处把同一件事
列为未决；③ 标题写着「本轮新增四项」而本节实际已有 12 个编号项；④ 结案注记里抄走的向量计数
（53/18/18）已被后续批次改成 56/20/20——散文抄单源的值，R9-B41 同族。
①②③都是「开放清单没有单源」的产物，所以 §4.0 表成为「还剩哪些事要人点头」的唯一依据。

五条判据，每条都在 `tests/python/ledger_decision_status_test.py` 里以内存态注入证伪并各带正面控制：
① 表在位、非空、ID 唯一且从 D1 连续 ⇒ 数不出任何一行就是判定面塌缩（exit 2，不判「通过」）；
② 每行六列齐全，`状态` 必须**恰好等于**封闭词表里的一项，且事项/状态两列不得含闭环措辞（已定的事
   要摘出表、到 §三 留案，不能既占开放位又声称已落地）；
③ 双向引用：表里的 ID 必须被表外散文引用（没人引用的行＝残骸），散文引用的 ID 必须在表里（散文里
   私开一个决定＝下一轮数不到它）；§四 未划线的**叶子条目**必须引用至少一个 ID；
④ 指针落得下：表行「最近复核」与 §四 已划线条目里的 `§3.nn` 必须能在同一份台账解析到 `### 3.nn`
   小节（R9-B52 那次「§3.48 整节缺失却被 §二/§四 三处引用」就是这个形状），`§五 Qn` 必须是真队列行，
   `§四 第 N 项` 必须落在本节编号项范围内且编号连续；
⑤ 别名矛盾：表行的别名（`Qn` / `R9-XX-n` / `AEG-nnn` / `AX-nn`）不得出现在 §四 已划线条目、§五 已划线
   队列行或 §六「复核后判定为不成立」里——那三处都是书面结论，同一别名既开着又已闭＝台账自相矛盾。

退出码：0=通过 / 1=违规 / 2=环境错误或判定面塌缩。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import verify_ledger_queue_status as queue

ROOT = Path(__file__).resolve().parents[1]
LEDGER_GLOB = "docs/audit/full-audit-*.md"
DECISION_HEAD = re.compile(r"^## 四、待用户定稿", re.M)
SIX_HEAD = re.compile(r"^## 六、", re.M)
TABLE_ROW = re.compile(r"^\| (D\d+) \|")
COLUMNS = 6
OPEN_STATES = ("待定稿", "待裁决", "需产品决策", "待设备", "需用户在场", "待排期")
CLOSED_WORDS = ("已落地", "已定稿并落地", "已闭", "结案", "判成不做", "不成立", "已并入")
D_REF = re.compile(r"\bD\d+\b")
POINTER = re.compile(r"§(3\.\d+)")
SIX_REF = re.compile(r"§六")
QUEUE_REF = re.compile(r"§五 (Q\d+)")
SECTION4_REF = re.compile(r"§四 第 (\d+) 项")
HEADING = re.compile(r"^### (3\.\d+)", re.M)
TOP_ITEM = re.compile(r"^- ", re.M)
SUB_ITEM = re.compile(r"^[ \t]+(\d+)\. ", re.M)
STRUCK_HEAD = re.compile(r"^(?:-|[ \t]+\d+\.)[ \t]+~~|^[ \t]*~~")
ALIAS = re.compile(r"\b(?:R\d+-[A-Z]+-\d+|AEG-\d+|AX-\d+|Q\d+)\b")
QUEUE_ROW = re.compile(r"^- (?:~~)?(Q\d+)")


def section_body(text: str) -> str:
    """§四 正文（到下一个 `## ` 为止）；没有这一节返回空串——早期轮次不进判定面。"""
    start = DECISION_HEAD.search(text)
    if not start:
        return ""
    stop = re.search(r"^## ", text[start.end():], re.M)
    return text[start.end(): start.end() + stop.start()] if stop else text[start.end():]


def table_rows(body: str) -> list[list[str]]:
    """`| Dn |` 行 → 各列文本（表外散文不参与本函数的判定）。"""
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in body.splitlines()
        if TABLE_ROW.match(line)
    ]


def item_blocks(body: str) -> list[tuple[str, str]]:
    """§四 的**叶子条目** → (条目头行, 整块)。

    两级结构：`- ` 是顶层，`  1. ` 是子项。带子项的父条目**展开成子项**、父条目本身不判——
    §四 的父条目是「外部审计里不能照做的条目」这类清单标题，状态与出处都写在子项上。
    扫描面因此先按顶层切块，再在块内找子项；反过来先把子项当条目头，父块会被砍成零长度，
    「父条目不判」这条就不成立（本批第一版栽在这里：判据把清单标题当成未划线条目判红了）。
    块边界取「下一条条目头」——少了这层，一条未划线条目就能借下一条的 ID 引用或指针过判据
    （R9-B81 为 §五 的同一件事补过第三层边界）。
    """
    tops = [match.start() for match in TOP_ITEM.finditer(body)]
    blocks: list[tuple[str, str]] = []
    for index, start in enumerate(tops):
        end = tops[index + 1] if index + 1 < len(tops) else len(body)
        block = body[start:end]
        children = [match.start() for match in SUB_ITEM.finditer(block)]
        if not children:
            blocks.append((block.splitlines()[0], block))
            continue
        for child_index, child in enumerate(children):
            child_end = children[child_index + 1] if child_index + 1 < len(children) else len(block)
            child_block = block[child:child_end]
            blocks.append((child_block.splitlines()[0], child_block))
    return blocks


def pointer_check(pointers: set[str], queue_refs: set[str], heads: set[str], known_q: set[str], where: str) -> list[str]:
    if not pointers and not queue_refs:
        return [f"{where} 没有可解析的出处指针（`§3.nn` / `§五 Qn`）"]
    problems = [f"{where} 的指针 `§{pointer}` 在本文件里解析不到 `### {pointer}` 小节"
                for pointer in sorted(pointers - heads)]
    problems += [f"{where} 指向的 §五 {ref} 不是一条队列行"
                 for ref in sorted(queue_refs - known_q)]
    return problems


def queue_ids(text: str) -> tuple[set[str], list[tuple[str, str]]]:
    all_ids: set[str] = set()
    struck: list[tuple[str, str]] = []
    for head, block in queue.queue_blocks(text):
        match = QUEUE_ROW.match(head)
        if not match:
            continue
        all_ids.add(match.group(1))
        if head.startswith("- ~~"):
            struck.append((head, block))
    return all_ids, struck


def conclusion_faces(text: str, body: str) -> dict[str, str]:
    """别名不得出现的三处**书面结论面**：§四 已划线条目 + §五 已划线队列行 + §六「不成立」清单。

    分面返回而不是拼成一个字符串：撞车时要能点名是哪一面判红的，把三段拼起来就只剩一条模糊措辞。
    """
    decided_rows = [block for head, block in item_blocks(body) if STRUCK_HEAD.match(head)]
    _all, struck_queue_rows = queue_ids(text)
    six = SIX_HEAD.search(text)
    six_body = ""
    if six:
        stop = re.search(r"^## ", text[six.end():], re.M)
        six_body = text[six.end(): six.end() + stop.start()] if stop else text[six.end():]
    return {
        "§四 已划线条目": "\n".join(decided_rows),
        "§五 已划线队列行": "\n".join(block for _head, block in struck_queue_rows),
        "§六 不成立清单": six_body,
    }


def check_ledger(text: str, name: str) -> tuple[list[str], int]:
    body = section_body(text)
    rows = table_rows(body)
    if not rows:
        return [], 0
    heads = set(HEADING.findall(text))
    known_q, _struck_rows = queue_ids(text)
    problems: list[str] = []

    ids = [row[0] for row in rows if row]
    if len(set(ids)) != len(ids):
        problems.append(f"表里 ID 重复：{sorted({item for item in ids if ids.count(item) > 1})}")
    if ids != [f"D{n}" for n in range(1, len(ids) + 1)]:
        problems.append(f"表 ID 必须从 D1 连续编号，现是 {ids}")

    prose = "\n".join(line for line in body.splitlines() if not line.strip().startswith("|"))
    prose_refs = set(D_REF.findall(prose))
    table_refs = set(ids)
    for missing in sorted(table_refs - prose_refs):
        problems.append(f"表里 {missing} 没被 §四 散文引用——残骸要摘表，不该留在开放面里")
    for extra in sorted(prose_refs - table_refs):
        problems.append(f"§四 散文引用了 {extra}，但表里没有这一行——开放决定必须先进表")

    for head, block in item_blocks(body):
        pointers = set(POINTER.findall(block))
        queue_refs = set(QUEUE_REF.findall(block))
        if STRUCK_HEAD.match(head):
            problems += pointer_check(pointers, queue_refs, heads, known_q, f"§四 已划线条目「{head.strip()[:34]}」")
        elif not D_REF.findall(block):
            problems.append(f"§四 未划线条目没有引用 §4.0 表的任何 ID：{head.strip()[:44]}")

    numbered = sorted({int(match.group(1)) for match in SUB_ITEM.finditer(body)})
    for ref in SECTION4_REF.finditer(text):
        wanted = int(ref.group(1))
        if not numbered:
            problems.append(f"引用了「§四 第 {ref.group(1)} 项」，但本节一个编号项都没有")
        elif wanted > max(numbered):
            problems.append(f"引用了「§四 第 {ref.group(1)} 项」，但本节编号项只到 {max(numbered)}")
        elif wanted not in numbered:
            problems.append(f"引用了「§四 第 {ref.group(1)} 项」，本节编号里没有这一号（现有 {numbered}）")

    faces = conclusion_faces(text, body)
    for cells in rows:
        if len(cells) != COLUMNS:
            problems.append(f"表行「{cells[0] if cells else '?'}」有 {len(cells)} 列，应为 {COLUMNS} 列"
                            "（ID/事项/状态/别名/为什么不能自己定/最近复核）")
            continue
        row_id, matter, state, alias, _why, review = cells
        if state not in OPEN_STATES:
            problems.append(f"{row_id} 的状态「{state}」不在词表 {OPEN_STATES} 里")
        for word in CLOSED_WORDS:
            if word in state or word in matter:
                problems.append(f"{row_id} 写着闭环措辞「{word}」——已定的事要摘出 §4.0 表并在 §三 留案，"
                                "不能既占开放位又声称已落地")
        problems += pointer_check(set(POINTER.findall(review)), set(QUEUE_REF.findall(review)),
                                  heads, known_q, f"{row_id} 的「最近复核」列")
        for token in sorted(set(ALIAS.findall(alias))):
            pattern = re.compile(rf"\b{re.escape(token)}\b")
            for face_name, face_text in faces.items():
                hit = next((line.strip()[:60] for line in face_text.splitlines() if pattern.search(line)), "")
                if hit:
                    problems.append(
                        f"{row_id} 的别名 {token} 已被{face_name}的书面结论收走（同一件事既开着又已闭）：{hit}")
                    break
    return problems, len(rows)


def run() -> int:
    ledgers = sorted(ROOT.glob(LEDGER_GLOB))
    if not ledgers:
        print(f"[环境错误] 找不到任何台账：{LEDGER_GLOB}", file=sys.stderr)
        return 2
    judged = 0
    rows_total = 0
    problems: list[str] = []
    for ledger in ledgers:
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        if not DECISION_HEAD.search(text):
            continue
        found, rows = check_ledger(text, ledger.name)
        if rows == 0:
            print(f"[环境错误] {ledger.name} 的 §四 有「待用户定稿」标题却数不出一条 `| Dn |` 表行"
                  "——判定面塌了，不作通过判定", file=sys.stderr)
            return 2
        judged += 1
        rows_total += rows
        problems += found
    if judged == 0:
        print("[环境错误] 没有任何台账带 §四「待用户定稿」——本判据无事可做就等于没接上", file=sys.stderr)
        return 2
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    print(f"[ok] §四 开放决策清单对账通过（{judged} 份台账、{rows_total} 条开放决策；"
          "状态词、双向引用、指针与别名矛盾全部判过且零违规）")
    return 0


if __name__ == "__main__":
    sys.exit(run())

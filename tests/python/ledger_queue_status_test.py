"""台账 §五 队列状态判据的用例（R9-B52 / 第九轮自查）。

两条判据都要**能红**，所以每条都配内存态注入（不改工作树）+ 一条正面控制：
①划线的行必须有能解析到的 `§3.nn` 指针（§3.48 那种「整节缺失却被三处引用」就是它要抓的）；
②没划线的行必须写明为什么还开着（否则下一轮按 §五 数规模会虚高，把做完的事再派一遍）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ledger_queue_status as g

ROUND9 = ROOT / "docs" / "audit" / "full-audit-2026-10-10-round9.md"
HEAD = "## 五、待回读队列（示例）\n"

STRUCK_OK = HEAD + "- ~~Q1 R9-XX-1~~ **已闭（R9-B1 / §3.1）** | P2 | 正文\n\n### 3.1 R9-B1：示例小节\n正文\n"
UNSTRUCK_OK = HEAD + "- Q2 R9-XX-2 | P2 | 正文：要改默认放行方向 ⇒ §四 待裁决。\n\n### 3.2 x\n"
STRUCK_DANGLING = HEAD + "- ~~Q3 R9-XX-3~~ **已闭（§3.48）** | P2 | 正文\n\n### 3.1 另一节\n"
UNSTRUCK_NO_WORD = HEAD + "- Q4 R9-XX-4 | P2 | `some/file.kt:1`：现象描述，没有任何状态说明。\n\n### 3.1 另一节\n"


def test_real_round9_ledger_passes() -> None:
    text = ROUND9.read_text(encoding="utf-8")
    assert g.violations(text) == []
    assert g.run() == 0


@pytest.mark.parametrize(
    ("text", "expect"),
    [
        (STRUCK_OK, []),
        (UNSTRUCK_OK, []),
        (STRUCK_DANGLING, "没有能解析到的 §3.nn 指针"),
        (UNSTRUCK_NO_WORD, "没有开放状态词"),
    ],
)
def test_the_two_rules_fire_only_where_they_should(text: str, expect: list[str] | str) -> None:
    found = g.violations(text)
    if isinstance(expect, str):
        assert len(found) == 1 and expect in found[0], found
        return
    assert found == [], found


def test_queue_section_is_bounded_at_the_next_top_level_heading() -> None:
    """§五 最后一条行不许把 §六 的正文当自己的状态说明（那里出现「待裁决」是常态）。"""
    text = HEAD + "- Q8 R9-XX-8 | P2 | 没有状态词的一行。\n\n## 六、复核后判定为不成立\n待裁决的东西都在这里。\n"
    blocks = g.queue_blocks(text)
    assert len(blocks) == 1 and "待裁决" not in blocks[0][1], "队列段没在下一个 `## ` 处收尾"
    assert len(g.violations(text)) == 1


def test_row_block_is_bounded_at_the_next_subsection_heading() -> None:
    """R9-B81：块还必须在下一个 `### ` 处收尾——本文件 docstring 从 R9-B52 就这么声明过，实树没做。

    后果不是理论上的：第九轮把 §3.20 之后的批次记录物理写进了 §五 的字节范围，缺这层边界时
    队列最后一条行的块吞掉整段 §三 尾巴（真台账实测 174947 字符 vs 该行自身正文 1170 字符），
    于是「未划线的行必须写明为什么开着」在那一行**空转**——下面的注入就是当时的假绿形态。
    """
    text = (HEAD + "- Q9 R9-XX-9 | P2 | 没有状态词的一行。\n\n"
            "### 3.9 R9-B9：批次记录\n那条批注里写着「待裁决」三个字。\n")
    blocks = g.queue_blocks(text)
    assert len(blocks) == 1, blocks
    assert "待裁决" not in blocks[0][1], "块没在 `### ` 处收尾，§三 的正文被当成活行的状态说明"
    assert len(g.violations(text)) == 1, "借来的状态词把这条活行判成了「已说明为什么开着」"


def test_real_ledger_last_row_does_not_swallow_the_batch_log() -> None:
    """正面控制：真台账的最后一条行只该有它自己的正文那么长。

    这条钉的是**规模**而不是内容——上一批把边界修好后，如果哪天又有人把 §三 写回 §五 范围内
    并同时放宽块边界，行数看不出来、块长会立刻膨胀。
    """
    blocks = g.queue_blocks(ROUND9.read_text(encoding="utf-8"))
    assert blocks, "§五 一条行都数不出来"
    assert len(blocks[-1][1]) < 6000, f"最后一条行的块有 {len(blocks[-1][1])} 字符——又在吞 §三 尾巴"


def test_pointers_are_resolved_inside_the_same_ledger_only() -> None:
    """指针必须在**同一份**台账里有对应小节——跨文件借用一个号就是假闭环。"""
    assert g.violations(STRUCK_DANGLING), "注入没被判出来"
    fixed = STRUCK_DANGLING.replace("### 3.1 另一节", "### 3.48 R9-B48：补开的小节")
    assert g.violations(fixed) == [], "补上真实小节后不该再判红"


def test_unstruck_rows_need_an_explicit_reason() -> None:
    """状态词表是**封闭**的：造一个词（「已完成」）不算交代为什么还开着。

    注意 §五 的标题本身含「待回读」这个词（它是队列段的身份），所以判据只扫**行块**——
    标题不算状态词，这一点由本用例的行块内容保证（块里没有任何词表项）。
    """
    text = HEAD + "- Q5 R9-XX-5 | P2 | 正文：这一步已完成，剩下没人说。\n"
    blocks = g.queue_blocks(text)
    assert len(blocks) == 1
    assert not any(word in blocks[0][1] for word in g.OPEN_STATE_WORDS), "本用例的语料自己含了状态词，判不了事"
    found = g.violations(text)
    assert len(found) == 1 and "没有开放状态词" in found[0], found


def test_ledgers_without_a_queue_section_are_out_of_scope() -> None:
    """轮 6 的 `## 五、` 是「被推翻的子代理结论」，不是队列段。

    这不是放宽判据：把它算进判定面的后果是**当场触发塌缩分支**（本批实测第一版就栽在这里，
    exit 2 报「有 §五 却数不出一条队列行」）。判定面的边界要按实树的标题写。
    """
    for ledger in sorted((ROOT / "docs" / "audit").glob("full-audit-*.md")):
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        if "待回读队列" not in text:
            assert g.queue_blocks(text) == [], f"{ledger.name} 不该进判定面"


def test_collapse_is_an_environment_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = tmp_path / "docs" / "audit"
    audit.mkdir(parents=True)
    (audit / "full-audit-x.md").write_text(HEAD + "（这一版还没登记队列行）\n", encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    assert g.run() == 2
    # 反向：一份连 §五 都没有的台账不能把判据变成「无事可做也算过」
    (audit / "full-audit-x.md").write_text("## 一、别的\n正文\n", encoding="utf-8")
    assert g.run() == 2


def test_row_block_boundaries_are_real() -> None:
    """块边界收在「下一条队列行」——不能一条行的状态词被下一条借走。"""
    text = HEAD + "- Q6 R9-XX-6 | P2 | 没有状态词的一行。\n- Q7 R9-XX-7 | P2 | 有状态词：待裁决。\n"
    blocks = g.queue_blocks(text)
    assert len(blocks) == 2
    found = g.violations(text)
    assert len(found) == 1 and "Q6" in found[0], found


def test_queue_row_count_is_not_collapsed() -> None:
    """正面控制：真 §五 必须数出成规模的行，否则「全部通过」是空对空。"""
    blocks = g.queue_blocks(ROUND9.read_text(encoding="utf-8"))
    assert len(blocks) >= 40, f"§五 只数出 {len(blocks)} 条队列行——提取口径坏了"
    struck = [h for h, _ in blocks if re.match(r"^- ~~Q\d+", h)]
    assert len(struck) >= 30, f"划线的行只有 {len(struck)} 条，与落地规模不符"

def test_duplicate_section_number_is_reported() -> None:
    """同一个 `### 3.nn` 出现两次 ⇒ 判红：`§3.nn` 指针照样解析得到，但没人知道指哪一节。"""
    text = HEAD + """- ~~Q20 R9-XX-20~~ **本批已闭（§3.5）** | P2 | 正文

### 3.5 R9-B5：甲批
正文

### 3.5 R9-B5：乙批
正文
"""
    found = g.violations(text)
    assert len(found) == 1 and "出现 2 次" in found[0], found


def test_gaps_in_section_numbering_are_not_judged() -> None:
    """反向控制：跳号不判红——历史上撤销过编号，判跳号只会逼人回填一个假编号。"""
    text = HEAD + """- ~~Q21 R9-XX-21~~ **本批已闭（§3.9）** | P2 | 正文

### 3.9 R9-B9：只有这一节
正文
"""
    assert g.violations(text) == []

"""台账 §四 开放决策清单判据的用例（R9-B92 / R9-DOC-25）。

五条判据每条都以内存态注入证伪，并各带正面控制——特别要防「恒绿」：判据读的是这张表与这几处结论面，
如果提取口径坏了（表数不出来、条目块切错、结论面为空），五条会一起变成空转，而「零违规」看起来正好
像「台账很干净」。`test_judgment_surface_is_not_empty` 与 `test_parent_item_is_not_judged` 就是两条墓碑。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ledger_decision_status as g

ROUND9 = ROOT / "docs" / "audit" / "full-audit-2026-10-10-round9.md"
ROW = "| D1 | Android 要不要内置名单 | 需产品决策 | Q8, R9-CS-8 | 出厂内容是发布决定 | §3.1、§五 Q8 |"

BASE = f"""## 四、待用户定稿（示例）

### 4.0 待用户给话清单

| ID | 事项 | 状态 | 别名 | 为什么不能自己定 | 最近复核 |
| --- | --- | --- | --- | --- | --- |
{ROW}

开放项只有 §4.0 表那一条（D1）。

- ~~**R9-CS-7**~~ **已定稿并落地（§3.1）** | P3 | 正文
- **要不要接联网源**＝§4.0 表 D1 的另一半：要先定签名与断网策略。
- **外部审计里不能照做的条目**：
  1. ~~**AEG-002**~~ **已落地（§3.1）**：正文。
  2. **AEG-009：要不要默认需确认**＝§4.0 表 D1 的代价面：属默认放行方向。

### 3.1 R9-B1：示例小节
正文

## 五、待回读队列（示例）

- Q8 R9-CS-8 | P2 | 正文：机制可落，名单内容待裁决。
- ~~Q9 R9-CS-9~~ **已闭（§3.1）** | P2 | 正文：旧案。

## 六、复核后判定为不成立
- 「子资源层应该上拦截器」不成立（第九轮 R9-B88）：代价落在每个请求。
"""


def mutated(old: str, new: str) -> str:
    assert old in BASE, f"注入锚点不在示例台账里：{old[:40]}"
    return BASE.replace(old, new, 1)


def violations(text: str) -> list[str]:
    found, rows = g.check_ledger(text, "fixture.md")
    assert rows >= 1, "示例台账没数出表行——提取口径坏了"
    return found


def test_base_fixture_is_clean() -> None:
    """正面控制：示例台账本身必须零违规，否则下面每条注入都不成立。"""
    assert violations(BASE) == []


def test_real_round9_ledger_passes() -> None:
    text = ROUND9.read_text(encoding="utf-8")
    found, rows = g.check_ledger(text, ROUND9.name)
    assert found == [], found
    assert rows == 4, f"§4.0 表现读 {rows} 行，与 §3.92 记录的规模不符（改了表要同改这条）"
    assert g.run() == 0


def test_judgment_surface_is_not_empty() -> None:
    """正面控制：真台账的段边界、叶子条目、结论面与 §五 队列行都要有规模。"""
    text = ROUND9.read_text(encoding="utf-8")
    body = g.section_body(text)
    assert body and "## 五、" not in body, "§四 段边界没在下一个 `## ` 处收尾"
    blocks = g.item_blocks(body)
    assert len(blocks) >= 15, f"§四 只数出 {len(blocks)} 条叶子条目，提取口径可疑"
    assert sum(1 for head, _ in blocks if g.STRUCK_HEAD.match(head)) >= 10
    faces = g.conclusion_faces(text, body)
    assert set(faces) == {"§四 已划线条目", "§五 已划线队列行", "§六 不成立清单"}
    assert all(face.strip() for face in faces.values()), {k: len(v) for k, v in faces.items()}
    known, struck = g.queue_ids(text)
    assert len(known) >= 50 and len(struck) >= 40, (len(known), len(struck))


def test_parent_item_is_not_judged() -> None:
    """清单标题（带子项的父条目）不判——本批第一版把它当未划线条目判红过。"""
    heads = [head for head, _ in g.item_blocks(g.section_body(BASE))]
    assert not any(head.startswith("- **外部审计") for head in heads), "父条目被当成叶子判了：它的正文里没有 D 引用"
    assert any(head.startswith("  1. ") for head in heads), "子项没被展开成叶子条目"


def test_state_word_must_be_in_the_closed_list() -> None:
    found = violations(mutated(ROW, ROW.replace("需产品决策", "已完成")))
    assert len(found) == 1 and "不在词表" in found[0], found


def test_closed_word_cannot_occupy_an_open_row() -> None:
    found = violations(mutated(ROW, ROW.replace("Android 要不要内置名单", "Android 内置名单已落地")))
    assert len(found) == 1 and "闭环措辞" in found[0], found


def test_row_nobody_cites_is_debris() -> None:
    """残骸行：表里多一条而散文不提——下一轮按表数「还剩几件事」就会虚高。"""
    extra = BASE.replace("开放项只有", ROW.replace("D1", "D2") + "\n\n开放项只有")
    found = violations(extra)
    assert any("D2" in line and "没被 §四 散文引用" in line for line in found), found


def test_prose_cannot_open_a_decision_without_a_row() -> None:
    """反方向：散文里私开一个 D7 而不进表＝这张表不再是「还剩哪些事」的依据。"""
    found = violations(mutated("（D1）", "（D1、D7）"))
    assert len(found) == 1 and "散文引用了 D7" in found[0], found


def test_open_item_must_point_at_the_table() -> None:
    found = violations(mutated("＝§4.0 表 D1 的另一半", "＝另一半"))
    assert any("没有引用 §4.0 表的任何 ID" in line for line in found), found


def test_struck_item_pointer_must_resolve() -> None:
    """R9-B52 的 §3.48 形状在 §四 的复现：写着「已定稿并落地（§3.48）」而那一节整节不存在。"""
    found = violations(mutated("已定稿并落地（§3.1）", "已定稿并落地（§3.48）"))
    assert len(found) == 1 and "解析不到 `### 3.48`" in found[0], found


def test_six_alone_is_not_a_pointer() -> None:
    """§六 单独不算出处：结案必须能回读到「哪一批判的」，所以 §3.nn 或 §五 Qn 才是可解析指针。"""
    found = violations(mutated("已定稿并落地（§3.1）", "已定稿并落地（§六）"))
    assert len(found) == 1 and "没有可解析的出处指针" in found[0], found


def test_section4_item_reference_must_resolve() -> None:
    cites = "开放项见 §四 第 1 项；本表说明：开放项只有"
    assert violations(mutated("开放项只有", cites)) == []  # 第 1 项真在，指得动
    over = violations(mutated("开放项只有", cites.replace("第 1 项", "第 9 项")))
    assert any("只到 2" in line for line in over), over
    dropped = BASE.replace("开放项只有", cites).replace(
        "  1. ~~**AEG-002**~~ **已落地（§3.1）**：正文。\n", "")
    assert any("编号里没有这一号" in line for line in violations(dropped)), violations(dropped)


@pytest.mark.parametrize(
    ("alias", "expect"),
    [
        ("Q9", "别名 Q9 已被"),
        ("R9-CS-9", "别名 R9-CS-9 已被"),
    ],
)
def test_alias_colliding_with_a_written_conclusion(alias: str, expect: str) -> None:
    """判据⑤——本批真抓到的那两条就是这个形状（UniFFI 撞 §五 已划线的 Q26、dependencyLocking 撞 §四 第 4 项）。"""
    found = violations(mutated("| Q8, R9-CS-8 |", f"| {alias} |"))
    assert any(expect in line for line in found), found
    assert len([line for line in found if "别名" in line]) == 1, found


def test_alias_may_appear_in_an_open_claim() -> None:
    """不哭狼：别名指向一个**还开着**的条目是正常的（AEG-009 在 §四 第 2 项里未划线）。"""
    found = violations(mutated("| Q8, R9-CS-8 |", "| AEG-009 |"))
    assert found == [], found
    # 同一位置换成已划线的 AEG-002 就必须红——两条一起构成「判据认得出方向，不是见别名就咬」
    assert any("别名 AEG-002 已被" in line for line in violations(mutated("| Q8, R9-CS-8 |", "| AEG-002 |")))


def test_queue_pointer_must_name_a_real_row() -> None:
    found = violations(mutated("§3.1、§五 Q8", "§3.1、§五 Q99"))
    assert len(found) == 1 and "不是一条队列行" in found[0], found


def test_review_pointer_must_resolve() -> None:
    found = violations(mutated("§3.1、§五 Q8", "§3.9、§五 Q8"))
    assert len(found) == 1 and "解析不到 `### 3.9`" in found[0], found


def test_ids_must_be_unique_and_contiguous() -> None:
    duplicated = violations(mutated(ROW, ROW + "\n" + ROW))
    assert any("ID 重复" in line for line in duplicated), duplicated
    gap = violations(mutated(ROW, ROW.replace("| D1 |", "| D3 |")))
    assert any("从 D1 连续" in line for line in gap), gap
    short = mutated(ROW, "| D1 | Android 要不要内置名单 | 需产品决策 | Q8 | 发布决定 |")
    assert any("应为 6 列" in line for line in violations(short))


def test_collapse_is_an_environment_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = tmp_path / "docs" / "audit"
    audit.mkdir(parents=True)
    (audit / "full-audit-x.md").write_text("## 四、待用户定稿\n\n这一节只有散文，没有表。\n", encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    assert g.run() == 2, "有 §四 标题却数不出一条表行＝判定面塌缩，不能算通过"
    (audit / "full-audit-x.md").write_text("## 一、别的\n正文\n", encoding="utf-8")
    assert g.run() == 2, "没有任何台账带 §四「待用户定稿」＝本判据没接上"


def test_early_rounds_are_out_of_scope() -> None:
    """轮 6/7/8 的 `## 四、` 是别的主题（前五轮复核、本轮 P2），不进判定面。"""
    for ledger in sorted((ROOT / "docs" / "audit").glob("full-audit-*.md")):
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        if "待用户定稿" not in text.split("\n## 五、")[0].split("## 四、")[-1]:
            assert g.section_body(text) == "", f"{ledger.name} 不该进判定面"


def test_gate_is_on_the_pr_face() -> None:
    """接入面：写好了没人跑＝没判（R9-CI-4 同族）。"""
    face = (ROOT / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8")
    assert "python scripts/verify_ledger_decision_status.py" in face, "本门禁没接进 PR 常跑面"
    registry = (ROOT / "contracts" / "ci" / "gate-execution-face.yaml").read_text(encoding="utf-8")
    assert "verify_ledger_decision_status.py" not in registry, "已可达的门禁不得留在登记表里"

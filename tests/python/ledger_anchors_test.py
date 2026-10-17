"""§五 活行 `file:line` 锚与符号锚可解析性判据的用例（R9-B81 / R9-B83，台账 Q69 第一、三候选）。

每条判据都有内存注入证伪，另配正面控制（现树必须真数出成规模的锚）。范围口径本身也由用例钉住：
**已划线的行不参与判**——它们引的是当时的行号，代码一改必然悬空，全量改写历史违反
「翻转不静默删行」，开豁免表又造出下一个假绿源。哪天要改这个范围，用例会先红。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ledger_anchors as g
import verify_ledger_queue_status as q

ROUND9 = ROOT / "docs" / "audit" / "full-audit-2026-10-10-round9.md"
HEAD = "## 五、待回读队列（示例）\n"
# 一条一定解析得到的锚：本门禁自己的第一行。
SELF_ANCHOR = "scripts/verify_ledger_anchors.py:1"
SELF_SYMBOL = "scripts/verify_ledger_anchors.py::check_row"
OK_ROW = HEAD + f"- Q1 R9-XX-1 | P2 | `{SELF_ANCHOR}`：现象描述，需用户裁决。\n\n### 3.1 x\n"


def real_index() -> dict[str, list[Path]]:
    return g.name_index()


def test_real_round9_live_rows_have_resolvable_anchors() -> None:
    text = ROUND9.read_text(encoding="utf-8")
    problems, rows, anchors, symbol_rows = g.violations(text, real_index())
    assert problems == [], "活行的 file:line 锚失账：" + "；".join(problems)
    # 塌缩守卫原来写成 `anchors >= 20`——那是与**队列规模**耦合的绝对下界，于是每结一条案
    # 就少一截，最后会因为「把活干完了」而红（R9-B86 结案时实测：7 条活行降到 5 条、
    # 锚从 20+ 降到 19，正红）。这是「门禁把现状钉成期望值」的亲戚。
    # 改成相对判据：每条活行至少一处锚（判据本身的规则，塌成 0 处照样红），
    # 而「活行被清空」这种真事件由 `rows >= 1` 兜住——真要清空第九轮，改这一行必须写理由。
    assert rows >= 1, "判定面塌了：§五 没有任何活行（本轮若真已清空，改这里要写理由）"
    assert anchors >= rows, f"判定面塌了：活行 {rows} 条却只有 {anchors} 处锚——至少每条一处"
    assert symbol_rows == g.MIN_SYMBOL_ROWS, f"现树符号锚行 {symbol_rows} 与登记值不符"
    assert g.run() == 0


def test_open_row_without_any_anchor_is_reported() -> None:
    text = HEAD + "- Q2 R9-XX-2 | P2 | 只有现象与位置名，一个行号锚都没写，需用户裁决。\n\n### 3.1 x\n"
    problems, _, _, _ = g.violations(text, real_index())
    assert len(problems) == 1 and "没有任何 file:line 锚" in problems[0], problems


def test_anchor_beyond_the_end_of_the_file_is_reported() -> None:
    # 本文件根本没有 99999 行——这正是 #218 那类「代码增删后没回读」的极限形态。
    text = HEAD + "- Q3 R9-XX-3 | P2 | `scripts/verify_ledger_anchors.py:99999-99999`：待裁决。\n"
    problems, _, _, _ = g.violations(text, real_index())
    assert len(problems) == 1 and "行号越界" in problems[0], problems


def test_missing_file_is_reported() -> None:
    text = HEAD + "- Q4 R9-XX-4 | P2 | `scripts/verify_ledger_no_more.py:12`：待裁决。\n"
    problems, _, _, _ = g.violations(text, real_index())
    assert len(problems) == 1 and "实树里没有的文件" in problems[0], problems


def test_ambiguous_bare_filename_is_reported(tmp_path: Path) -> None:
    """裸名在两处同名 ⇒ 读者得自己猜是哪一个，判红。实测现树：队列行（含已划线）里 0 处多义，
    22 处全在 §三 的批次记录里——本门禁只判活行，那些仍由 §三 自证（见下一条用例）。"""
    index = {"broker.rs": [tmp_path / "a" / "broker.rs", tmp_path / "b" / "broker.rs"]}
    for path in index["broker.rs"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\ny\n", encoding="utf-8")
    text = HEAD + "- Q5 R9-XX-5 | P2 | `broker.rs:1`：待裁决。\n"
    problems, _, _, _ = g.violations(text, index)
    assert len(problems) == 1 and "无法唯一解析" in problems[0], problems


def test_cited_range_of_blank_lines_is_reported(tmp_path: Path) -> None:
    empty = tmp_path / "empty.cs"
    empty.write_text("using System;\n\n\n\n\nvoid F() {}\n", encoding="utf-8")
    index = {"empty.cs": [empty]}
    text = HEAD + "- Q6 R9-XX-6 | P2 | `empty.cs:2-5`：待裁决。\n"
    problems, _, _, _ = g.violations(text, index)
    assert len(problems) == 1 and "全是空行" in problems[0], problems
    # 反向控制：同样的锚指到真代码行就不该红
    assert g.violations(HEAD + "- Q6 R9-XX-6 | P2 | `empty.cs:6`：待裁决。\n", index)[0] == []


def test_symbol_anchor_resolves_and_counts_the_row() -> None:
    text = HEAD + f"- Q7 R9-XX-7 | P2 | `{SELF_SYMBOL}`：符号锚形式，待裁决。\n"
    problems, rows, anchors, symbol_rows = g.violations(text, real_index())
    assert problems == [] and rows == 1 and anchors == 1 and symbol_rows == 1, (problems, symbol_rows)


def test_renamed_symbol_is_reported() -> None:
    """函数改名/删除而锚没跟着改 ⇒ 红（这正是行号锚漏掉的那一类，R9-B83 要抓的就是它）。"""
    text = HEAD + "- Q8 R9-XX-8 | P2 | `scripts/verify_ledger_anchors.py::check_row_that_never_existed`：待裁决。\n"
    problems, _, _, symbol_rows = g.violations(text, real_index())
    assert len(problems) == 1 and "剔注释后的代码" in problems[0], problems
    assert symbol_rows == 0, "解析失败的符号锚不得计入棘轮"


def test_symbol_only_in_a_comment_is_not_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """注记里写着符号名**不算**证据（R9-B39 那个病的对偶）——口径单源 `text_anchors.strip_comments`。"""
    src = tmp_path / "note.cs"
    src.write_text("// Greeter 只在注记里出现\nvoid F() {}\n", encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    text = HEAD + "- Q9 R9-XX-9 | P2 | `note.cs::Greeter`：待裁决。\n"
    problems, _, _, _ = g.violations(text, {"note.cs": [src]})
    assert len(problems) == 1 and "剔注释后的代码" in problems[0], problems


def test_ambiguous_symbol_anchor_path_is_reported(tmp_path: Path) -> None:
    index = {"dup.kt": [tmp_path / "one" / "dup.kt", tmp_path / "two" / "dup.kt"]}
    for path in index["dup.kt"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fun dup() = 1\n", encoding="utf-8")
    text = HEAD + "- Q10 R9-XX-10 | P2 | `dup.kt::dup`：待裁决。\n"
    problems, _, _, _ = g.violations(text, index)
    assert len(problems) == 1 and "多义裸名" in problems[0], problems


def test_ratchet_is_pinned_in_both_directions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """等号而不是下界：多锚了不登记也要红（fixture 自带一份小实树，不靠真仓的文件解析）。"""
    audit = tmp_path / "docs" / "audit"
    audit.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "foo.py").write_text("def check_row():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    (audit / "full-audit-x.md").write_text(
        HEAD + "- Q11 R9-XX-11 | P2 | `scripts/foo.py::check_row`：待裁决。\n"
        "- Q12 R9-XX-12 | P2 | `scripts/foo.py:1`：待裁决。\n", encoding="utf-8")
    monkeypatch.setattr(g, "MIN_SYMBOL_ROWS", 2)
    assert g.run() == 1, "锚了 2 行却登记 1 条（或反之）必须红"
    monkeypatch.setattr(g, "MIN_SYMBOL_ROWS", 1)
    assert g.run() == 0, "与登记值一致时不该因为别的行而红"


def test_struck_rows_are_deliberately_out_of_scope(tmp_path: Path) -> None:
    """划线的行引失锚**不判红**——这是范围口径，不是漏判（理由见模块 docstring）。"""
    text = HEAD + "- ~~Q13 R9-XX-13~~ **本批已闭（§3.9）** | P2 | `scripts/verify_ledger_no_more.py:99999`。\n"
    problems, rows, anchors, symbol_rows = g.violations(text, real_index())
    assert problems == [] and (rows, anchors, symbol_rows) == (0, 0, 0)


def test_collapsed_scan_surface_is_an_environment_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = tmp_path / "docs" / "audit"
    audit.mkdir(parents=True)
    (audit / "full-audit-x.md").write_text(HEAD + "（这一版还没登记队列行）\n", encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    assert g.run() == 2
    (audit / "full-audit-x.md").write_text("## 一、别的\n正文\n", encoding="utf-8")
    assert g.run() == 2


def test_gate_is_on_the_pr_face() -> None:
    """接入面：本门禁必须挂在 PR 判定面的 contracts.yml 里（R9-CI-4 同族——写好了没人跑＝没判）。"""
    face = (ROOT / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8")
    assert "python scripts/verify_ledger_anchors.py" in face, "本门禁没接进 PR 常跑面"
    # 可达就不许再进登记表（在册＝声称没人跑）
    registry = (ROOT / "contracts" / "ci" / "gate-execution-face.yaml").read_text(encoding="utf-8")
    assert "verify_ledger_anchors.py" not in registry, "已可达的门禁不得留在登记表里"
    assert q.QUEUE_HEAD.search(ROUND9.read_text(encoding="utf-8"))


def test_queue_head_boundary_still_bounds_live_rows() -> None:
    """与兄弟门禁的分工：本文件判锚，`## ` 收尾由队列状态门禁判——两边都得在。"""
    text = HEAD + f"- Q14 R9-XX-14 | P2 | `{SELF_ANCHOR}`：待裁决。\n## 六、复核后判定为不成立\n`x.kt:99999`\n"
    problems, _, anchors, _ = g.violations(text, real_index())
    assert problems == [] and anchors == 1, f"§六 的内容被吞进活行了：{problems} / {anchors}"

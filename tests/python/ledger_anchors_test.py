"""§五 活行 `file:line` 锚可解析性判据的用例（R9-B81 / 台账 Q69 第一半）。

四条判据每条都配内存态注入证伪 + 一条正面控制（现树必须真数出成规模的锚，否则
「全部通过」是空对空）。范围口径本身也由一条用例钉住：**已划线的行不参与判**——
它们引的是当时的行号，代码一改必然悬空，全量改写历史违反「翻转不静默删行」，
开豁免表又造出下一个假绿源。这条决定要哪天改，用例先红，逼下一个人读这段理由。
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
OK_ROW = HEAD + f"- Q1 R9-XX-1 | P2 | `{SELF_ANCHOR}`：现象描述，需用户裁决。\n\n### 3.1 x\n"


def real_index() -> dict[str, list[Path]]:
    return g.name_index()


def test_real_round9_live_rows_have_resolvable_anchors() -> None:
    text = ROUND9.read_text(encoding="utf-8")
    problems, rows, anchors = g.violations(text, real_index())
    assert problems == [], "活行的 file:line 锚失账：" + "；".join(problems)
    assert rows >= 1 and anchors >= 20, f"判定面塌了：活行 {rows} 条、锚 {anchors} 处"
    assert g.run() == 0


def test_open_row_without_any_anchor_is_reported() -> None:
    text = HEAD + "- Q2 R9-XX-2 | P2 | 只有现象与位置名，一个行号锚都没写，需用户裁决。\n\n### 3.1 x\n"
    problems, _, _ = g.violations(text, real_index())
    assert len(problems) == 1 and "没有任何 file:line 锚" in problems[0], problems


def test_anchor_beyond_the_end_of_the_file_is_reported() -> None:
    # 本文件根本没有 99999 行——这正是 #218 那类「代码增删后没回读」的极限形态。
    text = HEAD + "- Q3 R9-XX-3 | P2 | `scripts/verify_ledger_anchors.py:99999-99999`：待裁决。\n"
    problems, _, _ = g.violations(text, real_index())
    assert len(problems) == 1 and "行号越界" in problems[0], problems


def test_missing_file_is_reported() -> None:
    text = HEAD + "- Q4 R9-XX-4 | P2 | `scripts/verify_ledger_no_more.py:12`：待裁决。\n"
    problems, _, _ = g.violations(text, real_index())
    assert len(problems) == 1 and "实树里没有的文件" in problems[0], problems


def test_ambiguous_bare_filename_is_reported(tmp_path: Path) -> None:
    """裸名在两处同名 ⇒ 读者得自己猜是哪一个，判红。实测现树：队列行（含已划线）里 0 处多义，
    22 处全在 §三 的批次记录里——本门禁只判活行，那些仍由 §三 自证（见下一条用例）。"""
    index = {"broker.rs": [tmp_path / "a" / "broker.rs", tmp_path / "b" / "broker.rs"]}
    for path in index["broker.rs"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\ny\n", encoding="utf-8")
    text = HEAD + "- Q5 R9-XX-5 | P2 | `broker.rs:1`：待裁决。\n"
    problems, _, _ = g.violations(text, index)
    assert len(problems) == 1 and "无法唯一解析" in problems[0], problems


def test_cited_range_of_blank_lines_is_reported(tmp_path: Path) -> None:
    empty = tmp_path / "empty.cs"
    empty.write_text("using System;\n\n\n\n\nvoid F() {}\n", encoding="utf-8")
    index = {"empty.cs": [empty]}
    text = HEAD + "- Q6 R9-XX-6 | P2 | `empty.cs:2-5`：待裁决。\n"
    problems, _, _ = g.violations(text, index)
    assert len(problems) == 1 and "全是空行" in problems[0], problems
    # 反向控制：同样的锚指到真代码行就不该红
    assert g.violations(HEAD + "- Q6 R9-XX-6 | P2 | `empty.cs:6`：待裁决。\n", index)[0] == []


def test_struck_rows_are_deliberately_out_of_scope(tmp_path: Path) -> None:
    """划线的行引失锚**不判红**——这是范围口径，不是漏判（理由见模块 docstring）。"""
    text = HEAD + "- ~~Q7 R9-XX-7~~ **本批已闭（§3.9）** | P2 | `scripts/verify_ledger_no_more.py:99999`。\n"
    problems, rows, anchors = g.violations(text, real_index())
    assert problems == [] and rows == 0 and anchors == 0


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
    text = HEAD + f"- Q9 R9-XX-9 | P2 | `{SELF_ANCHOR}`：待裁决。\n## 六、复核后判定为不成立\n`x.kt:99999`\n"
    problems, _, anchors = g.violations(text, real_index())
    assert problems == [] and anchors == 1, f"§六 的内容被吞进活行了：{problems} / {anchors}"

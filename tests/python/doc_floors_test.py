"""README 下界抄写对账判据的用例（R9-B82 / 台账 §3.82）。

四条判据每条都有内存注入证伪，另有一条**回归锚**盯本门禁自己第一版的假绿：那一版按
「`label:` 之后第一个 `minimum:`」配对，猜出 `Core=160` 这种伪下界，而 160 恰好在 README
抄写的集合里 ⇒ 单向判据全绿。现在的 `test_call_sites_are_read_structurally` 就是那条假绿
的墓碑——它判的是**取数方式**，不是数值。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_doc_floors as g

README_TEXT = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
FLOORS = [
    ("契约向量份数", "scripts/verify_vector_consumers.py", 23),
    ("向量条目总数", "scripts/verify_vectors.py", 409),
    ("dotnet Core 发现数", "scripts/assert_test_counts.py", 700),
    ("dotnet Broker 发现数", "scripts/assert_test_counts.py", 160),
]
OK = ("机器判定的只有下界：`scripts/assert_test_counts.py`（Core ≥700 / Broker ≥160）、"
      "`scripts/verify_vector_consumers.py`（≥23 份）与 `scripts/verify_vectors.py`（≥409 条目）；"
      "各端实际条数看 CI 日志。\n- 下一条 bullet\n")


def test_real_readme_matches_real_tree() -> None:
    floors = g.real_floors()
    assert g.violations(README_TEXT, floors) == []
    assert g.run() == 0
    # 正面控制：判定面非空，且值确实来自实树常量而不是 fixture
    assert len(floors) >= 4, floors
    assert {v for _, _, v in floors} == {23, 160, 409, 700}, floors


def test_call_sites_are_read_structurally() -> None:
    """取数方式回归锚：Core/Broker 的值必须来自 composite action 的 `with:`，不是邻行猜的。"""
    minima = g.dotnet_floors()
    assert minima.get("Core") == {700}, minima
    assert minima.get("Broker") == {160}, minima
    # 别的 `label:` 键（runner 标签之类）不得混进来当调用点
    assert all(values for values in minima.values()), minima


def test_stale_number_is_reported() -> None:
    stale = OK.replace("≥409 条目", "≥222 条目")
    assert stale != OK, "注入锚点没命中——OK 里那条文案改了，这条用例就必须同改（否则它在判空气）"
    found = g.violations(stale, FLOORS)
    assert len(found) == 1 and "scripts/verify_vectors.py" in found[0], found


def test_wrong_owner_is_reported() -> None:
    """历史事故原样注入：份数挂在 verify_vectors.py 名下（实树单源在 consumers）。"""
    text = ("机器判定的只有下界：`scripts/assert_test_counts.py`（Core ≥700 / Broker ≥160）与 "
            "`scripts/verify_vectors.py`（向量 ≥21 份 / 条目 ≥222）；其余。\n- 下一条\n")
    found = g.violations(text, FLOORS)
    assert len(found) == 2, found            # 两个归属脚本各自双向对不上
    assert any("scripts/verify_vector_consumers.py" in line and "一个数都没有" in line
               for line in found), found
    assert any("多 [21, 222]" in line for line in found), found


def test_floor_under_a_script_that_owns_none_is_reported() -> None:
    """第三向：数字挂在一个实树没有任何下界的脚本名下（改脚本时把常量搬走就是这种形态）。"""
    text = ("机器判定的只有下界：`scripts/check_doc_claims.py`（≥500 条目）与 "
            "`scripts/assert_test_counts.py`（Core ≥700 / Broker ≥160）、"
            "`scripts/verify_vector_consumers.py`（≥23 份）与 `scripts/verify_vectors.py`（≥409 条目）；其余。\n- 下一条\n")
    real = g.real_floors()
    by_label = {label: value for label, _, value in real}
    # 这条判的是「归属错」，所以其余数字必须与实树一致——否则多出来的「数不对」会淹掉那一条真违规
    assert f"≥{by_label['契约向量份数']} 份" in text, real
    assert f"≥{by_label['向量条目总数']} 条目" in text, real
    found = g.violations(text, real)
    assert len(found) == 1 and "没有任何下界归它" in found[0], found


def test_unwired_extra_floor_is_reported() -> None:
    found = g.violations(OK.replace("Broker ≥160", "Broker ≥160 / 新增 ≥9999"), FLOORS)
    assert len(found) == 1 and "多 [9999]" in found[0], found


def test_call_site_divergence_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(g, "dotnet_floors", lambda: {"Core": {700, 800}})
    found = g.violations(README_TEXT, g.real_floors())
    assert any("多个 workflow 里不一致" in line for line in found), found


def test_missing_bullet_and_broken_sources_are_not_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert g.violations("## 别的段落\n没有那句话\n", FLOORS) == [
        "README 里找不到「机器判定的只有下界」那条 bullet——本判据的语料面已漂移"]
    audit = tmp_path / "README.md"
    audit.write_text("没有那句话\n", encoding="utf-8")
    monkeypatch.setattr(g, "README", audit)
    assert g.run() == 1, "语料面漂移该判红而不是「无事可做算过」"

    def boom(*_a: str) -> int:
        raise ValueError("常量取不到")

    monkeypatch.setattr(g, "python_const", boom)
    assert g.run() == 2, "实树常量取不到＝环境错误，不能判通过"


def test_gate_is_on_the_pr_face() -> None:
    """接入面：写好了没人跑＝没判（R9-CI-4 同族）。"""
    face = (ROOT / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8")
    assert "python scripts/verify_doc_floors.py" in face, "本门禁没接进 PR 常跑面"
    registry = (ROOT / "contracts" / "ci" / "gate-execution-face.yaml").read_text(encoding="utf-8")
    assert "verify_doc_floors.py" not in registry, "已可达的门禁不得留在登记表里"

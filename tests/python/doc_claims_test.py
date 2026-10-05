# doc_claims_test.py —— 第八轮 B8：文档计数声明门禁的掏空面自证。
#
# 与 gate_hollowness_test.py 同一口径：不验证「现在绿」，先验证「掏空它会红」。
# 本门禁特有的失效形态是「提取不到声明」（正则失配 / 全部被判历史性），那会让它
# 退化成永远绿的文件存在性检查——正是它要替代的那种假绿。
from __future__ import annotations

import check_doc_claims as cdc
import pytest


def _first(text: str) -> tuple[int, int, bool]:
    claims = cdc.extract_claims(text)
    assert claims, f"未提取到声明：{text!r}"
    return claims[0]


def test_stale_count_is_flagged():
    claims = cdc.extract_claims("- CI：**13 workflow 分层**\n")
    assert claims == [(1, 13, False)]
    assert cdc.violations_for("docs/a.md", claims, 15) == [
        "docs/a.md:1 声明 13 个 workflow，实树为 15"]


def test_matching_count_is_not_flagged():
    claims = cdc.extract_claims("发布门禁 15 个 workflow 分层 ✅\n")
    assert cdc.violations_for("README.md", claims, 15) == []


def test_claim_inside_dated_version_entry_is_a_snapshot():
    """CHANGELOG 结构：日期版本标题下的无日期子节仍属该条目——回改等于篡改历史。"""
    text = "## beta.21 (2026-09-07)\n### 工程\n- 12 个 workflow 补 timeout\n"
    assert _first(text) == (3, 12, True)
    assert cdc.violations_for("CHANGELOG.md", cdc.extract_claims(text), 15) == []


def test_dated_entry_boundary_is_the_heading_level():
    """同级的无日期标题会把日期条目弹出标题链——其后陈述回到判定面（豁免不外溢）。"""
    text = ("## beta.21 (2026-09-07)\n### 工程\n- 12 个 workflow\n"
            "## 当前口径\n- 12 个 workflow\n")
    assert cdc.extract_claims(text) == [(3, 12, True), (5, 12, False)]


def test_inline_date_alone_does_not_exempt():
    """行内提到某个日期不得换取豁免——实测失放形态正是这种：
    「**13 workflow 分层**（WB-160，2026-10-01 审计对齐实树）」是现行陈述，
    日期只是它的出处，不是它的生日。判据只认标题链。"""
    line = "- CI：**13 workflow 分层**（WB-160，2026-10-01 审计对齐实树）\n"
    assert cdc.extract_claims(line) == [(1, 13, False)]
    assert len(cdc.violations_for("docs/architecture-overview.md",
                                 cdc.extract_claims(line), 15)) == 1


def test_item_id_is_not_mistaken_for_a_count():
    """「WB-214 workflow 计数回归」里的 214 是条目号，不是数量声明（实测误报形态）。"""
    assert cdc.extract_claims("修复即回归：WB-214 workflow 计数回归；其余 9 项缓修\n") == []


def test_fenced_block_is_not_scanned():
    text = "```\n13 workflow\n```\n真声明：14 workflow\n"
    assert cdc.extract_claims(text) == [(4, 14, False)]


@pytest.mark.parametrize("line", [
    "13 workflow", "13 个 workflow", "13个workflow", "**13 workflow 分层**",
])
def test_count_claim_spellings_are_all_matched(line):
    """形态覆盖：中文量词/无空格/加粗包裹都须在面内（漏一种即一个盲区）。"""
    assert _first(line + "\n")[1] == 13


def test_empty_surface_is_env_error(monkeypatch):
    monkeypatch.setattr(cdc, "workflow_count", lambda: 15)
    monkeypatch.setattr(cdc, "list_markdown_files", lambda: [])
    assert cdc.main([]) == 2


def test_zero_judged_claims_is_env_error(tmp_path, monkeypatch):
    """提取面塌缩（声明全部被判历史性）不得报绿——本门禁特有的掏空面。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(
        "## v1 (2026-01-02)\n- 15 workflow\n", encoding="utf-8")
    monkeypatch.setattr(cdc, "ROOT", tmp_path)
    monkeypatch.setattr(cdc, "workflow_count", lambda: 15)
    monkeypatch.setattr(cdc, "list_markdown_files", lambda: ["docs/a.md"])
    assert cdc.main([]) == 2


def test_main_reports_stale_docs(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("CI：13 workflow\n", encoding="utf-8")
    monkeypatch.setattr(cdc, "ROOT", tmp_path)
    monkeypatch.setattr(cdc, "workflow_count", lambda: 15)
    monkeypatch.setattr(cdc, "list_markdown_files", lambda: ["docs/a.md"])
    assert cdc.main([]) == 1


def test_real_tree_claims_match_the_workflow_count():
    """真实面必须为绿——上面的反证用例只证「能红」，这条证「没变成噪声」。"""
    assert cdc.main([]) == 0


def test_workflow_count_is_computed_from_the_tree(tmp_path, monkeypatch):
    """计数由目录现算——写死常量的门禁不会随实树增删而红（R7-SH-01 同族失效）。"""
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    (d / "a.yml").write_text("", encoding="utf-8")
    (d / "b.yaml").write_text("", encoding="utf-8")
    (d / "notes.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(cdc, "WORKFLOWS_DIR", d)
    assert cdc.workflow_count() == 2


def test_real_workflow_count_is_not_hardcoded():
    """真实面同样按目录现算，且不少于第八轮实测的 15 个。"""
    yml = [p for p in (cdc.ROOT / ".github" / "workflows").glob("*")
           if p.suffix in (".yml", ".yaml")]
    assert cdc.workflow_count() == len(yml)
    assert len(yml) >= 15


def test_surface_is_markdown_only_and_excludes_archive():
    """扫描面只收 .md 且排除归档栈——legacy 只读冻结，不与正典实树对账。"""
    files = cdc.list_markdown_files()
    assert len(files) >= 50
    assert all(f.endswith(".md") for f in files)
    assert not [f for f in files if f.startswith("legacy/")]

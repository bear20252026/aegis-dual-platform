# ci_trigger_surface_test.py —— R9-B46（第九轮 Q48 / R9-CI-13）的门禁用例。
#
# ADR-007 D3 那句「门禁型 workflow 已全部移除 paths 过滤」曾经是**陈述**而不是事实
#（第九轮 R9-DOC-03 实测四处仍在过滤）。现在分类是登记表、判据是脚本，
# 所以每条都要能红：多一处过滤、少一个 PR 面、新增 workflow 没归类、
# 探测型混进 PR 面、一类里出现不存在的文件——五种都得判红（注入式，不改工作树）。
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ci_trigger_surface as g


@pytest.fixture(scope="module")
def real() -> tuple[set[str], dict, dict]:
    registry = g.load_registry()
    names = g.workflow_files()
    return names, registry, g.parsed_triggers(names)


def test_real_tree_passes(real) -> None:
    names, registry, triggers = real
    assert g.violations(names, registry, triggers) == []
    assert g.run() == 0


def test_gate_category_is_not_empty_and_really_unfiltered(real) -> None:
    """正面控制：如果 gates 是空集，上面那条绿灯就只是在判空气。"""
    names, registry, triggers = real
    assert set(registry["gates"]) == {
        "android-quality", "contracts", "core-rust", "agent-redteam", "supply-chain", "ci"}
    assert len(names) == 16
    for name in registry["gates"]:
        body = triggers[name]
        assert "pull_request" in body, f"{name} 不在 PR 面上判"
        assert g.filtered_events(body) == [], f"{name} 仍带触发过滤"


def test_registry_and_workflows_match_both_way(real) -> None:
    names, registry, _ = real
    registered = {n for group in registry.values() for n in group}
    assert registered == names, "登记表与实树不一致（双向对账的正面控制）"


def test_new_filter_on_a_gate_is_red(real) -> None:
    names, registry, triggers = real
    tampered = copy.deepcopy(triggers)
    tampered["contracts"] = {"push": {"paths": ["contracts/**"]}, "pull_request": {}}
    problems = g.violations(names, registry, tampered)
    assert any("contracts.yml" in p and "触发过滤" in p for p in problems), problems


def test_gate_losing_its_pr_trigger_is_red(real) -> None:
    """没有 PR 面的「门禁」等于不存在——比过滤更彻底的空判。"""
    names, registry, triggers = real
    tampered = copy.deepcopy(triggers)
    tampered["core-rust"] = {"push": {}, "schedule": [{"cron": "0 2 * * 1"}]}
    problems = g.violations(names, registry, tampered)
    assert any("core-rust.yml" in p and "pull_request" in p for p in problems), problems


def test_unclassified_new_workflow_is_red(real) -> None:
    names, registry, triggers = real
    grown = set(names) | {"nightly-lint"}
    triggers2 = copy.deepcopy(triggers)
    triggers2["nightly-lint"] = {"push": {}, "pull_request": {}}
    problems = g.violations(grown, registry, triggers2)
    assert any("未归类" in p and "nightly-lint" in p for p in problems), problems


def test_stale_registry_entry_is_red(real) -> None:
    """登记了不存在的 workflow＝过期声明，与悄悄扩面同等致命（R9-SH-7 口径）。"""
    names, registry, triggers = real
    stale = copy.deepcopy(registry)
    stale["gates"] = [*stale["gates"], "removed-workflow"]
    problems = g.violations(names, stale, triggers)
    assert any("已不成立" in p or "不存在" in p for p in problems), problems


def test_probe_appearing_on_pr_surface_is_red(real) -> None:
    names, registry, triggers = real
    tampered = copy.deepcopy(triggers)
    tampered["compat"] = {"schedule": [{"cron": "0 6 * * 1"}], "pull_request": {}}
    problems = g.violations(names, registry, tampered)
    assert any("compat.yml" in p and "必需检查" in p for p in problems), problems


def test_double_classification_is_red(real) -> None:
    names, registry, triggers = real
    both = copy.deepcopy(registry)
    both["builds"] = [*both["builds"], "ci"]
    problems = g.violations(names, both, triggers)
    assert any("归进多类" in p for p in problems), problems


def test_scalar_and_boolean_on_forms_are_parsed() -> None:
    """YAML 1.1 把裸 `on` 读成 True，`on: push` 又是标量——两种形态都得认。"""
    assert g.triggers_of({"on": "push"}) == {"push": {}}
    assert g.triggers_of({True: {"push": {"paths": ["a"]}}}) == {"push": {"paths": ["a"]}}
    assert g.filtered_events(g.triggers_of({True: {"push": {"paths-ignore": ["docs/**"]}}})) == ["push"]
    assert yaml.safe_load("on:\n  push: {}\n") is not None


def test_missing_registry_exits_2(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(g, "WORKFLOWS", tmp_path)
    monkeypatch.setattr(g, "REGISTRY", tmp_path / "nope.yaml")
    assert g.run() == 2
    monkeypatch.setattr(g, "WORKFLOWS", ROOT / ".github" / "workflows")
    monkeypatch.setattr(g, "REGISTRY", tmp_path / "categories.yaml")
    (tmp_path / "categories.yaml").write_text("gates: [ghost]\n", encoding="utf-8")
    assert g.run() in (1, 2)

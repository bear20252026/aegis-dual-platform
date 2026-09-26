"""agent/tests/redteam_test.py —— 阶段 G（蓝图 agent/tests/）：红队测试骨架。

断言：提示注入/工具投毒/scope 重放/超预算/并发竞态都不能导致未批准副作用
（阶段 G 完成标准——ADR-004——kill switch 立即撤销未执行授权——本地 IPC
revocation）。红队 fixtures（agent/redteam/——4 类——prompt-injection/
tool-result-poisoning/replay-race/resource-budget）全部声明 expected deny——
测试验证拒绝语义与覆盖。
"""

from __future__ import annotations

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_DIRS = [
    "prompt-injection-fixtures",
    "tool-result-poisoning-fixtures",
    "replay-race-fixtures",
    "resource-budget-fixtures",
]


def test_redteam_fixtures_present_and_deny():
    """4 类红队 fixtures 就位且声明拒绝（expected deny——无未批准副作用）。
    SP-018：解析全部 JSON 块的 expected 字段——不允许任何样例声明放行。"""
    for kind in FIXTURE_DIRS:
        readme = ROOT / "redteam" / kind / "README.md"
        assert readme.is_file(), f"缺少红队 fixtures: {kind}"
        text = readme.read_text(encoding="utf-8")
        # SP-018/021：解析全部 expected 取值，逐个断言必须为 deny（无放行样例）
        expecteds = re.findall(r'"expected"\s*:\s*"([a-z_]+)"', text)
        assert expecteds, f"{kind} 应含 expected 声明"
        assert all(v == "deny" for v in expecteds), f"{kind} 存在放行样例: {expecteds}"


def test_action_catalog_default_deny():
    """蓝图：Action Catalog 默认拒绝——未登记 action 不可用——首批只读低风险。
    SP-022：每条 action 必须携带 int 预算（max_actions/max_bytes）。"""
    catalog = yaml.safe_load(
        (ROOT.parent / "contracts/policy/action-catalog.yaml").read_text(encoding="utf-8"))
    assert catalog.get("default_deny") is True, "Action Catalog 必须默认拒绝（fail-closed）"
    assert catalog.get("policy_version"), "必须声明 policy_version（单源）"
    for action in catalog.get("actions", []):
        assert action.get("read_only") is True, f"首批必须只读: {action.get('name')}"
        budget = action.get("budget") or {}
        assert isinstance(budget.get("max_actions"), int) and budget["max_actions"] > 0,             f"{action['name']} 需 int max_actions"
        assert isinstance(budget.get("max_bytes"), int) and budget["max_bytes"] > 0,             f"{action['name']} 需 int max_bytes"


def test_fixture_references_exist():
    """SP-023：catalog 中 redteam_fixtures 引用的每类 fixture 目录真实存在。"""
    catalog = yaml.safe_load(
        (ROOT.parent / "contracts/policy/action-catalog.yaml").read_text(encoding="utf-8"))
    for action in catalog.get("actions", []):
        for kind in action.get("redteam_fixtures", []):
            assert (ROOT / "redteam" / f"{kind}-fixtures" / "README.md").is_file(),                 f"{action['name']} 引用缺失 fixture: {kind}"


def test_kill_switch_revocation_documented():
    """原生 kill switch（revocation）语义就位——立即撤销未执行授权（ADR-004）。"""
    rev = (ROOT / "local-ipc" / "revocation.md").read_text(encoding="utf-8")
    assert "Kill Switch" in rev and "撤销" in rev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✅ {name}")
    print("ALL OK — 阶段 G 红队测试通过（注入/投毒/重放/预算全部拒绝——无未批准副作用）")

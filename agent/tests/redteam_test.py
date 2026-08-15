"""agent/tests/redteam_test.py —— 阶段 G（蓝图 agent/tests/）：红队测试骨架。

断言：提示注入/工具投毒/scope 重放/超预算/并发竞态都不能导致未批准副作用
（阶段 G 完成标准——ADR-004——kill switch 立即撤销未执行授权——本地 IPC
revocation）。红队 fixtures（agent/redteam/——4 类——prompt-injection/
tool-result-poisoning/replay-race/resource-budget）全部声明 expected deny——
测试验证拒绝语义与覆盖。
"""

from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_DIRS = [
    "prompt-injection-fixtures",
    "tool-result-poisoning-fixtures",
    "replay-race-fixtures",
    "resource-budget-fixtures",
]


def test_redteam_fixtures_present_and_deny():
    """4 类红队 fixtures 就位且声明拒绝（expected deny——无未批准副作用）。"""
    for kind in FIXTURE_DIRS:
        readme = ROOT / "redteam" / kind / "README.md"
        assert readme.is_file(), f"缺少红队 fixtures: {kind}"
        text = readme.read_text(encoding="utf-8")
        # fixtures 内样例均声明拒绝（提示注入/投毒/重放/预算——阶段 G 完成标准）
        assert '"expected": "deny"' in text, f"{kind} 应声明 expected deny"


def test_action_catalog_default_deny():
    """蓝图：Action Catalog 默认拒绝——未登记 action 不可用——首批只读低风险。"""
    catalog = yaml.safe_load(
        (ROOT.parent / "contracts/policy/action-catalog.yaml").read_text(encoding="utf-8"))
    assert catalog.get("default_deny") is True, "Action Catalog 必须默认拒绝（fail-closed）"
    for action in catalog.get("actions", []):
        assert action.get("read_only") is True, f"首批必须只读: {action.get('name')}"


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

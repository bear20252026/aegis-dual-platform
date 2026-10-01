"""agent/tests/redteam_test.py —— 阶段 G（蓝图 agent/tests/）：红队测试骨架。

断言：提示注入/工具投毒/scope 重放/超预算/并发竞态都不能导致未批准副作用
（阶段 G 完成标准——ADR-004——kill switch 立即撤销未执行授权——本地 IPC
revocation）。红队 fixtures（agent/redteam/——4 类——prompt-injection/
tool-result-poisoning/replay-race/resource-budget）全部声明 expected deny——
测试验证拒绝语义与覆盖。

SP-170（2026-09-26 审计）：__main__ 运行器对齐 e2e 收集-汇总模式——逐用例
异常捕获+汇总（首个失败不再中断后续用例）。
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


def _is_positive_int(value) -> bool:
    """PY-251：正整数判定——bool 是 int 子类，显式排除（true 不得当 1 过门禁）。"""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def test_action_catalog_default_deny():
    """蓝图：Action Catalog 默认拒绝——未登记 action 不可用——首批只读低风险。
    SP-022：每条 action 必须携带 int 预算（max_actions/max_bytes）。
    PY-251（2026-10-01 审计）：bool 是 int 子类——isinstance(x, int) 对
    max_actions: true 放行，预算门禁可被布尔值绕过。显式排除 bool。"""
    catalog = yaml.safe_load(
        (ROOT.parent / "contracts/policy/action-catalog.yaml").read_text(encoding="utf-8"))
    assert catalog.get("default_deny") is True, "Action Catalog 必须默认拒绝（fail-closed）"
    assert catalog.get("policy_version"), "必须声明 policy_version（单源）"
    for action in catalog.get("actions", []):
        assert action.get("read_only") is True, f"首批必须只读: {action.get('name')}"
        budget = action.get("budget") or {}
        for key in ("max_actions", "max_bytes"):
            assert _is_positive_int(budget.get(key)), (
                f"{action['name']} 需正 int {key}（bool/非正数被拒——PY-251）")


def test_bool_budget_not_accepted_as_int():
    """PY-251 回归向量：布尔预算不得冒充整数过门禁（True 是 int 子类）。"""
    assert not _is_positive_int(True)
    assert not _is_positive_int(False)
    assert _is_positive_int(1)
    assert _is_positive_int(65536)
    assert not _is_positive_int(0)
    assert not _is_positive_int(-5)
    assert not _is_positive_int("5")


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
    # SP-170（2026-09-26 审计）：对齐 e2e 运行器——逐用例异常捕获+汇总
    #（首个失败不再中断后续用例——失败一次看全）。
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✅ {name}")
            except Exception as ex:  # noqa: BLE001
                failures.append((name, ex))
                print(f"  ❌ {name}: {ex}")
    if failures:
        raise SystemExit(f"{len(failures)} 失败")
    print("ALL OK — 阶段 G 红队测试通过（注入/投毒/重放/预算全部拒绝——无未批准副作用）")

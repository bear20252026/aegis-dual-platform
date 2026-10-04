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

import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_DIRS = [
    "prompt-injection-fixtures",
    "tool-result-poisoning-fixtures",
    "replay-race-fixtures",
    "resource-budget-fixtures",
]

# 被测对象为出厂模块（agent/broker.py），非本文件内脚手架——审计第六轮
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from broker import PolicyBroker, well_formed_action


def _expected_values(text: str) -> list[str]:
    """提取 README 全部 expected 声明值。

    PY-285（2026-10-02 审计）：捕获改 "([^"]+)"——原 [a-z_]+ 被末尾引号
    锚定，含连字符/数字/大小写的值（如 "allow-v2"）整个不进捕获——零断言
    面（静默逃逸：放行样例写在里面也不红）。改全字符捕获后逐个 == "deny"
    断言，任何形态的声明值都受门禁。
    """
    return re.findall(r'"expected"\s*:\s*"([^"]+)"', text)


def test_redteam_fixtures_present_and_deny():
    """4 类红队 fixtures 就位且声明拒绝（expected deny——无未批准副作用）。
    SP-018：解析全部 JSON 块的 expected 字段——不允许任何样例声明放行。"""
    for kind in FIXTURE_DIRS:
        readme = ROOT / "redteam" / kind / "README.md"
        assert readme.is_file(), f"缺少红队 fixtures: {kind}"
        text = readme.read_text(encoding="utf-8")
        # SP-018/021 + PY-285：解析全部 expected 取值（全字符捕获），
        # 逐个断言必须为 deny（无放行样例——非 [a-z_] 形态不再逃逸）
        expecteds = _expected_values(text)
        assert expecteds, f"{kind} 应含 expected 声明"
        assert all(v == "deny" for v in expecteds), f"{kind} 存在放行样例: {expecteds}"


def test_expected_value_capture_rejects_allow_variant():
    """PY-285 回归向量（负例）：含连字符的声明值 "allow-v2" 在旧正则
    （[a-z_]+ 锚定引号）下完全不进捕获——静默逃逸断言面；新捕获必须
    收到该值且判非 deny（放行样例必被门禁拒绝）。"""
    values = _expected_values('"expected": "allow-v2"\n"expected": "deny"\n')
    assert values == ["allow-v2", "deny"], "全字符捕获不得漏掉非 [a-z_] 形态"
    # allow-v2 必须被判非 deny（放行样例语义——若混入 fixtures 必红）
    assert not all(v == "deny" for v in values), "allow-v2 不得被当作 deny 放行"


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



# --------------------------------------------------------------------------- #
# 审计第六轮（2026-10-03）：fixtures 必须由 broker 真实执行
#
# 上方 test_redteam_fixtures_present_and_deny 只证明 README 散文里写了 deny
# ——没有任何载荷被喂给任何 broker，也没有任何可解析样例存在（本目录此前只有
# README.md）。那是纯粹的假保证：任何人新增一个实际会被放行的样例、只要把它
# 标注成 "expected": "deny"，门禁依旧全绿。下面补上行为面——解析各 kind 的
# 机器可读 fixtures.json，逐步构造 ProposedAction 调用**出厂** PolicyBroker
# （agent/broker.py，非测试内脚手架），断言精确决策串与声明一致。
# --------------------------------------------------------------------------- #

# 合法 expect 取值：allow 或 broker 的具名 deny 原因。禁止笼统的 "deny"——
# 断言必须钉到具体拒绝码，否则拒绝原因漂移（如 deny_replay 退化成
# deny_unknown）不会被发现。
ALLOW_EXPECT = "allow"
DENY_EXPECTS = frozenset({
    "deny_unknown", "deny_session", "deny_expired", "deny_max_ttl",
    "deny_policy", "deny_scope", "deny_generation", "deny_revoked",
    "deny_replay", "deny_budget", "deny_budget_bytes", "deny_canonical",
    "deny_tab", "deny_description_hash", "deny_payload",
})


def _fixture_files() -> list[tuple[str, pathlib.Path]]:
    return [(kind, ROOT / "redteam" / kind / "fixtures.json") for kind in FIXTURE_DIRS]


def _run_step(broker, step: dict) -> str:
    """执行一个步骤，返回 broker 实际决策串。"""
    if step.get("revoke"):
        broker.revoke()
    if "raw_payload" in step:
        return broker.decide(step["raw_payload"])
    return broker.evaluate(well_formed_action(**(step.get("overrides") or {})))


def test_redteam_fixtures_are_executed_by_broker():
    """红队载荷真实驱动出厂 broker——声明 deny 而实际 allow 即红。"""
    files = _fixture_files()
    missing = [str(path) for kind, path in files if not path.is_file()]
    assert not missing, f"缺少机器可读红队载荷文件（README 散文不算）: {missing}"

    total_cases = 0
    total_deny_steps = 0
    total_allow_controls = 0
    for kind, path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        cases = doc.get("cases") or []
        assert cases, f"{kind}: fixtures.json 无任何 case（空参数化=恒绿陷阱）"
        for case in cases:
            cid = case.get("id") or f"{kind}/{total_cases}"
            steps = case.get("steps") or []
            assert steps, f"{cid}: 无步骤"
            broker = PolicyBroker(**(case.get("broker") or {}))
            case_has_deny = False
            for index, step in enumerate(steps, start=1):
                expect = step.get("expect")
                assert expect is not None, f"{cid} step{index}: 未声明 expect"
                assert expect == ALLOW_EXPECT or expect in DENY_EXPECTS, (
                    f"{cid} step{index}: expect={expect!r} 非法——"
                    "必须是 allow 或 broker 具名拒绝码（禁止笼统 'deny'）")
                actual = _run_step(broker, step)
                assert actual == expect, (
                    f"{cid} step{index}: broker 实际判定 {actual!r} ≠ 声明 {expect!r}"
                    f" —— {'样例声明 deny 却实际放行（假保证）' if expect != ALLOW_EXPECT else '对照步骤被误拒'}")
                if expect == ALLOW_EXPECT:
                    total_allow_controls += 1
                else:
                    case_has_deny = True
                    total_deny_steps += 1
            assert case_has_deny, f"{cid}: 无拒绝步骤"
            total_cases += 1

    # broker 存活对照：若一个 allow 都没有，说明 broker 被整体改成一律拒绝，
    # 此时所有 deny 断言都是同义反复（拒绝源自 broker 失效而非攻击）——必须红。
    assert total_allow_controls >= len(files), (
        f"全量 fixtures 仅 {total_allow_controls} 个 allow 对照步骤——不足以证明"
        f" broker 存活（应至少每 kind 一个）")
    assert total_cases >= 8 and total_deny_steps >= 8, (
        f"红队覆盖塌缩：cases={total_cases} deny_steps={total_deny_steps}"
        "（低于第八轮审计基线，说明样例被删减）")

if __name__ == "__main__":
    # R7-TOOL-06（第七轮 2026-10-04）：删除本文件的 __main__ 手工运行器。
    # 本套件断言全为裸 `assert`，`python -O` / `PYTHONOPTIMIZE=1` 下在字节码
    # 编译期被整体剥离——原独立运行器实测「声明 deny 实 allow」的注入样例时
    # 打印 ALL OK、exit 0，等于一条环境变量摘掉整套行为门。唯一安全入口是
    # pytest（其重写器把 assert 改写成显式断言，-O 下仍红：实测 `-O -m pytest`
    # 照样 failed）。故直接执行本文件一律响亮失败，不再自行收集运行。
    print("本套件必须经 pytest 运行：python -m pytest -q agent/tests/redteam_test.py",
          file=sys.stderr)
    raise SystemExit(2)

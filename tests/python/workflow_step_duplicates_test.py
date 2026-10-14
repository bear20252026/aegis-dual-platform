# workflow_step_duplicates_test.py —— 本 job 内不得有第二份逐字相同步骤（R9-B61）的门禁用例。
#
# 判据本体在 scripts/verify_workflow_step_duplicates.py（口径与它的三条设计选择写在脚本头注）。
# 这里的形状与 core_unwired_modules_test.py / ffi_input_bounds_test.py 一致：先证现树全绿、
# 扫描面没塌缩，再把 R9-B60 留下的那个真实缺陷（同一步骤连同注记写了两遍）摆回内存里看它红不红，
# 最后配两条反向对照——跨 job 同体、同脚本不同参数——防判据退化成「任何重复文本都可疑」。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_workflow_step_duplicates as g


@pytest.fixture(scope="module")
def workflows():
    loaded = g.load_workflows()
    assert loaded, "workflow 面塌缩：一份定义都没读到"
    return loaded


def test_real_tree_has_no_duplicated_step_within_a_job(workflows):
    """现读：修完 contracts.yml 之后这条必须绿；把 R9-B60 那段改回两遍它就红。"""
    assert len(workflows) >= 16, f"workflow 面塌缩：只读到 {len(workflows)} 份"
    steps = sum(
        len((job or {}).get("steps") or [])
        for wf in workflows.values()
        for job in (wf.get("jobs") or {}).values()
        if isinstance(job, dict)
    )
    assert steps >= 150, f"步骤面塌缩：只数到 {steps} 步"
    assert g.scan(workflows) == []


def test_a_step_written_twice_is_caught(workflows):
    """反向锚：把 R9-B60 的真实形状摆回去（同一步骤两个副本，name/id 不同）。"""
    contracts = workflows["contracts.yml"]
    job = contracts["jobs"]["contract-source-of-truth"]
    steps = list(job["steps"])
    victim = next(
        (s for s in steps if isinstance(s, dict) and "path gate" in str(s.get("name"))),
        None,
    )
    assert victim is not None, "锚点步骤改名了——本用例的注入面不存在，需重判"
    twin = dict(victim)
    twin["id"] = str(victim.get("id", "")) + "-twin"
    twin["name"] = str(victim["name"]) + "（副本）"
    job["steps"] = steps + [twin]
    try:
        problems = g.scan({"contracts.yml": contracts})
        assert any(
            "同一份内容" in p and "contract-source-of-truth" in p for p in problems
        ), problems
    finally:
        job["steps"] = steps


def test_the_same_step_in_two_jobs_is_not_a_duplicate():
    """反向对照：dependency-relock 的三个「检出目标分支」分属三个 job ⇒ 不报。
    没有这条，判据就可能只是「任何重复文本都可疑」。"""
    relock = g.load_workflows()["dependency-relock.yml"]
    bodies = [
        g.step_fingerprint(step)
        for job in (relock.get("jobs") or {}).values()
        if isinstance(job, dict)
        for step in (job.get("steps") or [])
        if isinstance(step, dict) and step.get("name") == "检出目标分支"
    ]
    assert len(bodies) >= 2, "锚点形态变了——本对照用例需重判"
    assert len(set(bodies)) == 1, "三份副本内容已分叉，本用例的前提不再成立"
    assert g.scan({"dependency-relock.yml": relock}) == []


def test_a_repeated_script_with_different_arguments_is_not_a_duplicate():
    """`active_tree_gates.py` 在同一 job 里跑多次（ruff / bandit / py312）——
    同一条命令的第二份副本若参数不同就不是重复。"""
    contracts = g.load_workflows()["contracts.yml"]
    run_lines = [
        step["run"]
        for step in contracts["jobs"]["contract-source-of-truth"]["steps"]
        if isinstance(step, dict) and "active_tree_gates.py" in str(step.get("run", ""))
    ]
    assert len(run_lines) >= 2, "锚点形态变了——本对照用例需重判"
    assert len(set(run_lines)) == len(run_lines), "同一脚本被同参数调了两次，判据面需重判"
    assert g.scan({"contracts.yml": contracts}) == []


def test_a_changed_ingredient_makes_the_step_not_a_duplicate():
    """同体判据的边界：run 里多一行就不算重复——防判据写成「名字撞了就红」。"""
    contracts = g.load_workflows()["contracts.yml"]
    job = contracts["jobs"]["contract-source-of-truth"]
    steps = list(job["steps"])
    victim = next(
        s for s in steps if isinstance(s, dict) and "path gate" in str(s.get("name"))
    )
    moved = dict(victim)
    moved["name"] = str(victim["name"]) + "（第二处调用点）"
    moved["run"] = str(victim["run"]) + "\npython scripts/text_anchors.py\n"
    job["steps"] = steps + [moved]
    try:
        assert g.duplicates_in(job["steps"]) == []
    finally:
        job["steps"] = steps

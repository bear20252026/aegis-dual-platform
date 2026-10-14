"""`verify_workflow_script_paths.py` 的判据：调用点在**生效 cwd** 下必须真实存在。

起因是 R9-B60 的一次 dispatch 实证（run 38539285993）：`gradle-dependency-insight.yml`
的「工具类路径闭包」步骤写 `python scripts/verify_gradle_alert_scope_boundary.py`，
而那个 job 的 `defaults.run.working-directory: android` ⇒ runner 找的是
`android/scripts/…`，不存在 ⇒ 步骤 exit 2；同一步里的 `grep android/*/gradle.lockfile`
在 glob 展不开时先打印了一句 `(零命中)`——**把失败印成了一条看起来像结论的陈述**。
这条流自 R9-B49 加进来起从没跑通过，而它是 dispatch-only 诊断面：PR 面全绿，没人看它红。

所以这里判的是「能不能执行」，不是「有没有写」。每条判据都配注入 + 正面控制
（合法形态必须继续通过），否则判据只是「任何改动都红」。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_workflow_script_paths.py"
INSIGHT = ROOT / ".github" / "workflows" / "gradle-dependency-insight.yml"

sys.path.insert(0, str(ROOT / "scripts"))
from text_anchors import drop_line_comments  # shell/yaml 面用行级剔法（R9-B50 的口径）


def load():
    spec = importlib.util.spec_from_file_location("verify_workflow_script_paths", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vwsp = load()


def doc(job: dict) -> dict:
    return {"jobs": {"j": job}}


# ---------------------------------------------------------------- 现树

def test_real_tree_has_no_unexecutable_python_calls() -> None:
    assert vwsp.run() == 0, "实树里存在「在其生效 cwd 下不存在」的 python 调用点"


def test_gate_sees_a_nontrivial_surface() -> None:
    """判定面不能是空的：至少几十个工作流步骤被真的看过（面塌缩=恒绿）。"""
    files = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    steps = sum(
        1
        for path in files
        for job in (yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}).values()
        for step in (job.get("steps") or [])
        if isinstance(step.get("run"), str)
    )
    assert steps > 60, f"只数到 {steps} 个 run 步骤——提取口径可疑"


def test_the_insight_step_that_started_this_is_now_executable() -> None:
    """回归锚：正是那一步。判它要么 cwd 是根，要么路径带 `../`——两者都对，缺一个就红。"""
    workflow = yaml.safe_load(INSIGHT.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["insight"]["steps"]
    target = [s for s in steps if "工具类路径闭包" in str(s.get("name", ""))]
    assert len(target) == 1, "那一步不见了——本用例的锚要跟着改"
    body = drop_line_comments(target[0]["run"], "x.yml")
    assert "scripts/verify_gradle_alert_scope_boundary.py" in body, (
        "这一步不再跑 scope 门禁——那它的坐标归属证据就只剩 PR 面那一份，本用例的前提要重审")
    assert not vwsp.check_run(body, vwsp.effective_cwd(target[0], workflow["jobs"]["insight"], workflow),
                              "insight"), "这一步在它的 cwd 下不可执行——就是 R9-B60 抓到的那个形状"


# ---------------------------------------------------------------- cwd 解析

@pytest.mark.parametrize(("step", "job_cwd", "expected"), [
    ({}, "android", "android"),
    ({"working-directory": "."}, "android", "."),
    ({"working-directory": "core/rust-policy-core"}, "android", "core/rust-policy-core"),
    ({}, None, "."),
])
def test_effective_cwd_prefers_step_then_job_then_default(
    step: dict, job_cwd: str | None, expected: str) -> None:
    job = {"defaults": {"run": {"working-directory": job_cwd}}} if job_cwd else {}
    assert vwsp.effective_cwd(step, job, {}) == expected


def test_broken_shape_is_caught_and_fixed_shape_is_not() -> None:
    """同一句话、两种 cwd：`python scripts/x.py` 在 cwd=android 下红，在根下绿。

    这是本文件的核心对照——它证明判据抓的是 **cwd 与路径的组合**，不是字符串。
    """
    body = "python scripts/verify_versions.py"
    assert vwsp.check_run(body, "android", "x.yml :: j :: 0"), "cwd=android 时没抓住"
    assert vwsp.check_run(body, ".", "x.yml :: j :: 0") == [], "根 cwd 下被误判"


def test_parent_traversal_resolves() -> None:
    """`../scripts/x.py` 从 android/ 出发就是仓库根的那个文件——必须算可执行（正面控制）。"""
    assert vwsp.check_run("python ../scripts/verify_versions.py", "android", "x.yml") == []


def test_missing_script_is_caught_even_at_root() -> None:
    assert vwsp.check_run("python scripts/no_such_gate.py", ".", "x.yml :: j :: 0")


def test_expression_carrying_path_is_named_not_silently_passed() -> None:
    problems = vwsp.check_run(
        'python "${{ inputs.script }}" --check', ".", "x.yml :: j :: 0")
    assert problems and "展开" in problems[0], (
        f"带表达式的 python 调用没被点名（实得：{problems}）")


def test_non_path_python_forms_are_ignored() -> None:
    """`python -m`、heredoc 不是路径调用——判它们就是把判据指向不存在的形状。"""
    for body in ("python -m pytest tests/python -q", "python3 - <<'PY'",
                 "python3  -m ruff check ."):
        assert vwsp.check_run(body, ".", "x.yml") == [], body


def test_empty_jobs_is_a_violation_not_a_pass() -> None:
    assert vwsp.check_document({"jobs": {}}, Path("x.yml")), "零 jobs 必须被指出，否则面塌缩＝通过"
